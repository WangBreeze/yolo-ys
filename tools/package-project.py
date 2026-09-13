#!/usr/bin/env python3
"""Build a portable project ZIP; optional local data is included only by path."""

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import zipfile


def portable_path(path):
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    return all(part and not any(c in '<>:"\\|?*' or ord(c) < 32 for c in part)
               and not part.endswith((".", " ")) and part.split(".")[0].upper() not in reserved
               for part in path.parts)


def package(root, output, include=()):
    root, output = root.resolve(), output.resolve()
    if not output.is_relative_to(root) or output.exists():
        raise ValueError("output must be a new ZIP inside this project")
    roots = [root / p for p in ("game_agent", "configs", "docs", "examples", "tests", "tools", ".github", ".agents",
                                "README.md", "AGENTS.md", "pyproject.toml", "requirements.txt", ".gitignore",
                                "yolotest.py", "benchmark_yolo26.py", "people_2k.jpg", "memory/README.md", "memory/project.md")]
    for value in include:
        path = (root / value).resolve()
        if not path.is_relative_to(root) or path.parts[:len(root.parts)] != root.parts:
            raise ValueError("included paths must remain inside the project")
        relative = path.relative_to(root)
        if not relative.parts or relative.parts[0] in {".git", ".venv", ".codex"} or not path.exists():
            raise ValueError(f"unsupported include path: {value}")
        roots.append(path)
    files = set()
    for selected in roots:
        if not selected.exists():
            continue
        for path in (selected.rglob("*") if selected.is_dir() else [selected]):
            if path.is_symlink():
                raise ValueError("symlinks must be materialized before packaging")
            if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            if path.name.endswith((".local.toml", "-wal", "-shm")) or path.resolve() == output:
                continue
            relative = path.relative_to(root)
            if not portable_path(relative):
                raise ValueError(f"not a Windows-compatible filename: {relative}")
            files.add(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    hashes = {}
    names = [p.relative_to(root).as_posix().casefold() for p in files]
    if len(set(names)) != len(names):
        raise ValueError("filenames collide on case-insensitive Windows filesystems")

    def write_file(archive, path, name):
        digest = hashlib.sha256()
        info = zipfile.ZipInfo.from_file(path, name)
        info.compress_type = zipfile.ZIP_DEFLATED
        with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
            for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
                digest.update(block)
                target.write(block)
        hashes[name] = digest.hexdigest()

    try:
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
            for path in sorted(files):
                name = path.relative_to(root).as_posix()
                # A SQLite backup includes committed WAL content and closes handles before ZIP reads.
                if path.suffix in {".sqlite", ".sqlite3"}:
                    with tempfile.TemporaryDirectory() as folder:
                        snapshot = Path(folder) / "snapshot.sqlite3"
                        source_db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
                        target_db = sqlite3.connect(snapshot)
                        try:
                            source_db.backup(target_db)
                        finally:
                            source_db.close()
                            target_db.close()
                        write_file(archive, snapshot, name)
                else:
                    write_file(archive, path, name)
            archive.writestr("TRANSFER-MANIFEST.json", json.dumps({"schema_version": 1, "files": hashes},
                                                                 ensure_ascii=False, indent=2).encode("utf-8"))
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    digest = hashlib.sha256()
    with output.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return {"path": str(output), "files": len(hashes), "bytes": output.stat().st_size,
            "sha256": digest.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description="生成 Windows/Linux 项目迁移包，不包含运行环境和默认大模型")
    parser.add_argument("--output", default="memory/transfers/project-windows.zip")
    parser.add_argument("--include", action="append", default=[], help="另外包含的项目内数据、模型或数据库路径，可重复")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(package(root, root / args.output, args.include), ensure_ascii=False))


if __name__ == "__main__":
    main()
