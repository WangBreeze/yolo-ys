#!/usr/bin/env python3
"""Portable replacement for tools/video; reuses the project environment if present."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    executable = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not executable.is_file():
        executable = Path(sys.executable)
    env = dict(os.environ, PYTHONUTF8="1")
    return subprocess.call([str(executable), "-m", "game_agent", "--config", "configs/video.toml", *sys.argv[1:]],
                           cwd=root, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
