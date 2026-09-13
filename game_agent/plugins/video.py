from time import monotonic_ns

from ..contracts import Frame
from .base import Plugin


class VideoCapture(Plugin):
    ROLE = "capture"
    mode = "replay"

    def __init__(self, context, options):
        super().__init__(context, options)
        path = context.input_path(options["path"])
        if not path.is_file():
            raise FileNotFoundError(path)
        import cv2
        self.video = cv2.VideoCapture(str(path))
        if not self.video.isOpened():
            self.video.release()
            raise ValueError("cannot open video")
        self.sequence = 0

    def capture(self):
        captured_ns = monotonic_ns()
        ok, pixels = self.video.read()
        if not ok:
            return None
        self.sequence += 1
        h, w = pixels.shape[:2]
        return Frame(self.sequence, captured_ns, w, h, pixels=pixels)

    def close(self):
        self.video.release()
