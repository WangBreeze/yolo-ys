"""SQLite is authoritative. All reads are scoped by game/version/input profile."""

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from ..contracts import Plan, canonical
from .base import Plugin


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class SQLiteMemory(Plugin):
    ROLE = "memory"

    def __init__(self, context, options):
        super().__init__(context, options)
        path = context.output_path(options.get("path", "memory/game-agent.sqlite3"))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.db.close()
            raise ValueError(f"unsupported memory schema {version}; migration required")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        with self.db:
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY, game_key TEXT NOT NULL,
                    title TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES plans(id),
                    game_key TEXT NOT NULL, mode TEXT NOT NULL,
                    status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
                    plugins TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT);
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    kind TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_run ON events(run_id, sequence);
                CREATE INDEX IF NOT EXISTS runs_game ON runs(game_key, mode, status);
                PRAGMA user_version=1;
            ''')

    def remember(self, plan):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO plans VALUES (?, ?, ?, ?, ?)",
                            (plan.id, plan.game.key, plan.title, canonical(asdict(plan)), utc_now()))
        return plan.id

    def load_plan(self, plan_id, game):
        row = self.db.execute("SELECT body FROM plans WHERE id=? AND game_key=?",
                              (plan_id, game.key)).fetchone()
        if row is None:
            raise ValueError("plan not found in this game/version/profile")
        return Plan.from_dict(json.loads(row[0]))

    def recall(self, query, game, mode):
        rows = self.db.execute('''
            SELECT p.id, p.title,
                SUM(CASE WHEN r.status='success' AND r.mode=? THEN 1 ELSE 0 END) AS successes,
                SUM(CASE WHEN r.status IN ('blocked','error','timeout') AND r.mode=? THEN 1 ELSE 0 END) AS failures
            FROM plans p LEFT JOIN runs r ON p.id=r.plan_id
            WHERE p.game_key=? AND instr(lower(p.title), lower(?))>0
            GROUP BY p.id ORDER BY successes DESC, p.created_at DESC
        ''', (mode, mode, game.key, query)).fetchall()
        return [dict(row, status="verified" if row["successes"] else "candidate", mode=mode)
                for row in rows]

    def begin(self, plan, mode, plugins):
        self.remember(plan)
        run_id = uuid4().hex
        with self.db:
            self.db.execute('''INSERT INTO runs
                (id,plan_id,game_key,mode,status,plugins,started_at) VALUES (?,?,?,?,?,?,?)''',
                (run_id, plan.id, plan.game.key, mode, "running", canonical(plugins), utc_now()))
        return run_id

    def append(self, run_id, kind, data):
        with self.db:
            self.db.execute("INSERT INTO events(run_id,kind,body,created_at) VALUES (?,?,?,?)",
                            (run_id, kind, canonical(data), utc_now()))

    def finish(self, run_id, status, reason):
        with self.db:
            self.db.execute("UPDATE runs SET status=?,reason=?,finished_at=? WHERE id=?",
                            (status, reason, utc_now(), run_id))

    def examples(self, game, mode):
        if mode not in ("simulation", "live"):
            return []
        rows = self.db.execute('''
            SELECT e.body,r.id AS run_id,r.plugins FROM events e JOIN runs r ON r.id=e.run_id
            WHERE r.game_key=? AND r.mode=? AND r.status='success' AND e.kind='step_verified'
            ORDER BY e.sequence
        ''', (game.key, mode)).fetchall()
        return [dict(json.loads(r["body"]), run_id=r["run_id"], plugins=json.loads(r["plugins"]))
                for r in rows if json.loads(r["body"]).get("applied") is True]

    def export_run(self, run_id, path):
        run = self.db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise ValueError("unknown run")
        rows = self.db.execute("SELECT sequence,kind,body,created_at FROM events WHERE run_id=? ORDER BY sequence", (run_id,))
        with path.open("w", encoding="utf-8") as f:
            f.write(canonical({"run": dict(run)}) + "\n")
            for row in rows:
                f.write(canonical(dict(row, body=json.loads(row["body"]))) + "\n")

    def close(self):
        self.db.close()
