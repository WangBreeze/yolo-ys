#!/usr/bin/env python3
"""Opt-in real decoder/downloader/model smoke test; no desktop input or user media."""

import argparse
import functools
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", action="store_true", help="实际运行本地语音和视觉模型")
    parser.add_argument("--narration", help="可选：使用本地测试讲解 WAV，替代 espeak-ng")
    args = parser.parse_args()
    narrator = shutil.which("espeak-ng") or shutil.which("espeak")
    if not args.narration and not narrator:
        parser.error("需要 espeak-ng/espeak，或用 --narration 提供测试讲解音频；离线视觉训练检查不需要它")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        parser.error("请先让 ffmpeg 和 ffprobe 可在 PATH 中找到")
    import cv2
    import numpy as np
    from game_agent.config import load_config
    from game_agent.media import file_sha256
    from game_agent.runtime import Application
    from game_agent.video_library import VideoLibrary
    from game_agent.video_workflow import understand

    directory = ROOT / "memory/validation/video-stage1"
    directory.mkdir(parents=True, exist_ok=True)
    avi = directory / "synthetic-shop.avi"
    writer = cv2.VideoWriter(str(avi), cv2.VideoWriter_fourcc(*"MJPG"), 10, (1280, 720))
    assert writer.isOpened()
    for index in range(120):
        frame = np.full((720, 1280, 3), (30, 28, 24), np.uint8)
        cv2.putText(frame, "SYNTHETIC GAME TUTORIAL", (90, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (240, 240, 240), 3)
        title = ["1. OPEN SHOP", "2. BUY SWORD", "3. EQUIP SWORD"][index // 40]
        cv2.putText(frame, title, (90, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (60, 210, 255), 3)
        cv2.rectangle(frame, (150, 350), (850, 590), (90, 140, 50), -1)
        cv2.putText(frame, ["SHOP", "BUY SWORD - 100 GOLD", "SWORD EQUIPPED"][index // 40],
                    (190, 490), cv2.FONT_HERSHEY_SIMPLEX, 1.25, (255, 255, 255), 3)
        writer.write(frame)
    writer.release()
    wav = directory / "narration.wav"
    if args.narration:
        shutil.copyfile(Path(args.narration).resolve(), wav)
    else:
        subprocess.run([narrator, "-s", "150", "-w", str(wav),
                        "First, open the shop. Next, buy a sword for one hundred gold. Finally, open the inventory and equip the sword."], check=True)
    video = directory / "synthetic-shop.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(avi), "-i", str(wav),
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-c:a", "aac", "-af", "apad", "-t", "12", str(video)], check=True)
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def copyfile(self, source, outputfile):
            try:
                super().copyfile(source, outputfile)
            except (BrokenPipeError, ConnectionResetError):
                pass  # you-get closes its metadata probe before reading the body.
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=directory))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    context = load_config(ROOT / "configs/video.toml")
    # Keep validation assets separate from the user's tutorial catalog.
    context.config["video_library"]["path"] = "memory/validation/video-stage1/library"
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
    results = {}
    try:
        with Application(context) as app, VideoLibrary(context) as library:
            row = library.add(f"http://127.0.0.1:{server.server_port}/{video.name}", app.plugin("downloader"))
            stored = context.input_path(row["media"][0]["path"])
            assert file_sha256(stored) == file_sha256(video), "original bytes changed"
            assert row["category"] == "tutorial"
            results.update(download_original_bytes_verified=True, asset_id=row["id"],
                           fixture="synthetic shop UI + synthetic English narration, 12s 1280x720")
            if args.models:
                os.environ["HF_HUB_OFFLINE"] = os.environ["TRANSFORMERS_OFFLINE"] = "1"
                original_connect = socket.socket.connect
                def deny_network(sock, address):
                    if sock.family in (socket.AF_INET, socket.AF_INET6):
                        raise RuntimeError("offline validation: attempted network connection")
                    return original_connect(sock, address)
                socket.socket.connect = deny_network
                try:
                    first = understand(app, library, str(stored), refresh=True)
                    (directory / "cold-report.json").write_text(json.dumps(first, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    warm = understand(app, library, str(stored), refresh=True)
                    cached = understand(app, library, str(stored))
                finally:
                    socket.socket.connect = original_connect
                assert cached["cache_hit"]
                assert "controller" not in app.instances
                results.update(timings=first["timings"], warm_timings=warm["timings"],
                               cached_request_wall_s=cached["request_wall_s"],
                               summary=first["summary"], audio=first["audio"], report_json=first["report_json"],
                               cold_report_json=str(directory / "cold-report.json"),
                               offline_connect_guard=True)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
    (directory / "result.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
