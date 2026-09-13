import os

from ..contracts import State
from .base import Plugin


class YoloPerception(Plugin):
    ROLE = "perception"

    def __init__(self, context, options):
        super().__init__(context, options)
        weights = context.input_path(options["weights"])
        if not weights.is_file():
            raise FileNotFoundError(f"local weights required; no automatic download: {weights}")
        os.environ["YOLO_OFFLINE"] = "true"
        config_dir = context.output_path("memory/ultralytics")
        config_dir.mkdir(parents=True, exist_ok=True)
        os.environ["YOLO_CONFIG_DIR"] = str(config_dir)
        from ultralytics import YOLO
        self.model = YOLO(str(weights))

    def perceive(self, frame):
        if frame.pixels is None:
            raise ValueError("YOLO requires image pixels")
        result = self.model.predict(frame.pixels, device=self.options.get("device", 0),
                                    imgsz=self.options.get("imgsz", 640),
                                    conf=self.options.get("conf", 0.4), verbose=False)[0]
        facts, targets = dict(frame.facts), {}
        names = self.options.get("labels", {})
        # Explicit zero detections become false; unknown semantic facts stay unknown.
        for model_label in self.model.names.values():
            facts[names.get(model_label, model_label)] = False
        if result.boxes is not None:
            for box in result.boxes:
                label = names.get(result.names[int(box.cls.item())], result.names[int(box.cls.item())])
                facts[label] = True
                targets.setdefault(label, []).append(box.xyxyn[0].cpu().tolist())
        return State(frame.sequence, frame.captured_ns, facts, targets,
                     frame.focused, frame.window_id)

    def close(self):
        del self.model
