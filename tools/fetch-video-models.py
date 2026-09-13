#!/usr/bin/env python3
"""Explicit, one-time online setup. All weights/caches stay inside this project."""

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="下载第一阶段本地模型（约 5 GB）")
    parser.add_argument("--only", choices=["vision", "speech", "all"], default="all")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.environ["HF_HOME"] = str(root / "memory/cache/huggingface")
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    # Standard HTTP downloads work predictably through the local proxy and resume.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from huggingface_hub import snapshot_download
    models = {"vision": ("Qwen/Qwen3-VL-2B-Instruct", "Qwen3-VL-2B-Instruct"),
              "speech": ("Systran/faster-whisper-small", "faster-whisper-small")}
    for kind, (repo, directory) in models.items():
        if args.only not in {kind, "all"}:
            continue
        path = snapshot_download(repo_id=repo, local_dir=root / "memory/models" / directory,
                                 allow_patterns=["*.json", "*.safetensors", "*.bin", "*.txt"], max_workers=3)
        print(f"{kind}: {path}", flush=True)


if __name__ == "__main__":
    main()
