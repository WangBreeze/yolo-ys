#!/usr/bin/env python3
"""Create a project-local environment on Windows/Linux. No system package changes."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser(description="安装项目环境；先在当前 Python/Conda 环境配置所需 PyTorch")
    parser.add_argument("--profile", choices=["core", "video", "training", "windows", "all"], default="core")
    parser.add_argument("--isolated", action="store_true", help="不复用当前 Python/Conda 的已安装依赖")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    location = root / ".venv"
    executable = location / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if location.exists() and not executable.is_file():
        parser.error(".venv 不是当前系统可用的环境；请先移走它，再重新安装，不要复制另一系统的环境")
    if not executable.is_file():
        venv.EnvBuilder(with_pip=True, system_site_packages=not args.isolated).create(location)
    extras = {"core": "", "video": "video", "training": "video,training", "windows": "vision,windows",
              "all": "video,training,windows"}[args.profile]
    requirement = "." + (f"[{extras}]" if extras else "")
    subprocess.run([str(executable), "-m", "pip", "install", "--cache-dir", "memory/cache/pip", "-e", requirement],
                   cwd=root, check=True)
    if args.profile in {"video", "training", "all"} and not shutil.which("ffprobe"):
        print("依赖已安装；视频入库/理解还需 ffmpeg 的 ffprobe 可在 PATH 中找到。", file=sys.stderr)
        return 1
    print(f"项目环境已就绪：{executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
