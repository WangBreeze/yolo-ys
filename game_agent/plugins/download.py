"""you-get only retrieves original streams; never joins or re-encodes them."""

import importlib.util
import subprocess
import sys
from urllib.parse import urlsplit

from .base import Plugin


class YouGetDownloader(Plugin):
    ROLE = "downloader"

    def download(self, url, destination):
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("download needs an http(s) video URL")
        if importlib.util.find_spec("you_get") is None:
            raise ImportError("you-get 未安装：请运行 bash tools/setup-video.sh")
        command = [sys.executable, "-c", "from you_get import main; main()", "--no-merge", "--no-caption",
                   "--output-dir", str(destination)]
        if self.options.get("stream"):
            command += ["--format", self.options["stream"]]
        command.append(url)
        timeout = float(self.options.get("timeout_s", 3600))
        try:
            subprocess.run(command, check=True, timeout=timeout, stdout=sys.stderr)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("you-get 下载超时；未登记为完成的视频") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"you-get 下载失败（退出码 {exc.returncode}），请查看上方站点错误") from exc
