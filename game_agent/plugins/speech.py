"""Read audio locally; faster-whisper decodes in memory without changing media."""

import time

from .base import Plugin
from ..model_identity import model_identity


class FasterWhisperSpeech(Plugin):
    ROLE = "speech"

    def __init__(self, context, options):
        super().__init__(context, options)
        self.model = None

    def identity(self):
        return {"plugin": "faster-whisper.speech", "version": self.VERSION,
                **model_identity(self.context, self.options, "faster-whisper")}

    def transcribe(self, source):
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from faster_whisper import WhisperModel
        started = time.perf_counter()
        if self.model is None:
            self.identity()
            self.model = WhisperModel(str(self.context.input_path(self.options["model"])),
                                     device=self.options.get("device", "cpu"),
                                     compute_type=self.options.get("compute_type", "int8"),
                                     cpu_threads=self.options.get("cpu_threads", 4),
                                     local_files_only=True)
        load_s = time.perf_counter() - started
        started = time.perf_counter()
        segments, info = self.model.transcribe(
            str(source), beam_size=self.options.get("beam_size", 1),
            language=self.options.get("language") or None, vad_filter=True,
            condition_on_previous_text=False)
        rows = [{"start_s": s.start, "end_s": s.end, "text": s.text} for s in segments]
        return {"status": "transcribed", "language": info.language, "segments": rows,
                "metrics": {"model_load_s": load_s, "decode_and_asr_s": time.perf_counter() - started}}

    def close(self):
        self.model = None
