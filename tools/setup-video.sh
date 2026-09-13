#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# 先激活已有 yolo26 Conda 环境，可复用它的 CUDA/PyTorch。
VIDEO_PYTHON="${VIDEO_PYTHON:-python}"
if [[ ! -x .venv/bin/python ]]; then
    "$VIDEO_PYTHON" -m venv --system-site-packages .venv
fi
.venv/bin/python -m pip install --cache-dir memory/cache/pip -e '.[video]'
.venv/bin/python -m you_get --version
if ! command -v ffprobe >/dev/null; then
    echo '需要安装 ffmpeg（提供 ffprobe）；本脚本不更新系统。' >&2
    exit 1
fi
