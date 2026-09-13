"""A transparent behavior-memory baseline, not a neural network trainer."""

from collections import Counter, defaultdict

from ..contracts import canonical, example_key
from .base import Plugin


class ActionMemoryLearner(Plugin):
    ROLE = "learner"

    def train(self, examples, output):
        if not examples:
            raise ValueError("no verified successful transitions; execute demonstrations first")
        buckets = defaultdict(Counter)
        for row in examples:
            key = example_key(row["goal"], row["before"]["facts"])
            buckets[key][canonical(row["template"])] += 1
        import json
        model = {"schema_version": 1, "kind": "action-memory",
                 "game_key": self.context.game.key, "mode": self.context.mode,
                 "source_runs": sorted({x["run_id"] for x in examples}), "entries": {}}
        for key, votes in buckets.items():
            template, count = votes.most_common(1)[0]
            model["entries"][key] = {"template": json.loads(template), "count": count,
                                     "agreement": count / votes.total()}
        path = self.context.output_path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(canonical(model) + "\n", encoding="utf-8")
        temp.replace(path)
        return {"path": str(path), "examples": len(examples), "states": len(buckets),
                "kind": model["kind"]}
