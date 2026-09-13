"""Local video utilities shared by tutorial and capture adapters."""

import hashlib
import math
from pathlib import Path


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sample_video(path, max_frames=16, *, max_edge=None, hash_content=True):
    import cv2
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if type(max_frames) is not int or not 1 <= max_frames <= 64:
        raise ValueError("max_frames must be in [1, 64]")
    video = cv2.VideoCapture(str(path))
    try:
        if not video.isOpened():
            raise ValueError("video cannot be opened")
        count, fps = video.get(cv2.CAP_PROP_FRAME_COUNT), video.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(count) or count < 1 or not math.isfinite(fps) or fps <= 0:
            raise ValueError("video needs valid frame count and FPS")
        count = int(count)
        n = min(max_frames, count)
        indices = sorted({round(i * (count - 1) / max(1, n - 1)) for i in range(n)})
        frames = []
        # Nearby samples advance the current decoder without a new keyframe seek.
        # Distant samples seek directly, avoiding a full decode of long videos.
        next_index = 0
        for i in indices:
            gap = i - next_index
            if 0 <= gap <= max(1, int(fps)):
                for _ in range(gap):
                    if not video.grab():
                        raise ValueError(f"cannot advance to sampled video frame {i}")
            elif not video.set(cv2.CAP_PROP_POS_FRAMES, i):
                raise ValueError(f"cannot seek to sampled video frame {i}")
            ok, pixels = video.read()
            if not ok:
                raise ValueError(f"cannot decode sampled video frame {i}")
            next_index = i + 1
            if max_edge and max(pixels.shape[:2]) > max_edge:
                ratio = max_edge / max(pixels.shape[:2])
                pixels = cv2.resize(pixels, (max(1, round(pixels.shape[1] * ratio)),
                                            max(1, round(pixels.shape[0] * ratio))),
                                    interpolation=cv2.INTER_AREA)
            frames.append((i / fps, pixels))
        return {"sha256": file_sha256(path) if hash_content else None, "fps": fps, "frames": count,
                "duration_s": count / fps, "sampled_seconds": [t for t, _ in frames]}, frames
    finally:
        video.release()
