"""Budgeted stage-one understanding with content/revision-aware local caches."""

import json
import math
import os
import tempfile
import time
from pathlib import Path

from .contracts import canonical, fingerprint
from .media import file_sha256, sample_video
from .video_contracts import PRESETS, REPORT_SCHEMA, validate_description
from .video_library import probe


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
            temporary = f.name
            f.write(canonical(value) + "\n")
        os.replace(temporary, path)
    finally:
        # Windows cannot unlink an open NamedTemporaryFile: close before cleanup.
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cached_digest(path, cache):
    stat = path.stat()
    signature = [str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
    record_path = cache / "hashes" / (fingerprint(str(path)) + ".json")
    old = read_json(record_path)
    if old and old.get("signature") == signature:
        return old["sha256"]
    digest = file_sha256(path)
    after = path.stat()
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != tuple(signature[1:]):
        raise ValueError("视频正在写入，请下载完成后再读取")
    write_json(record_path, {"signature": signature, "sha256": digest})
    return digest


def transcript_input(path, duration):
    if path.suffix.lower() == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("transcript JSON must be a list of start_s/end_s/text objects")
    else:
        rows = [{"start_s": 0, "end_s": duration, "text": path.read_text(encoding="utf-8")}]
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("text"), str)
                or any(type(row.get(k)) not in (int, float) or not math.isfinite(row[k])
                       for k in ("start_s", "end_s"))
                or not 0 <= row["start_s"] <= row["end_s"] <= duration + 1):
            raise ValueError("invalid transcript timestamps/text")
    return {"status": "provided", "alignment": "timed" if path.suffix.lower() == ".json" else "whole_video",
            "segments": rows}


def markdown_report(report):
    lines = ["# 视频内容理解", "", report["summary"], "",
             f"模式：{report['preset']}；语音：{report['audio']['status']}；状态：候选理解，未验证操作。", ""]
    for segment in report["segments"]:
        lines += [f"## {segment['start_s']:.2f}–{segment['end_s']:.2f} 秒", "", segment["summary"], ""]
        for key, label in (("observations", "观察"), ("operation_intents", "可能的操作目的"), ("uncertainties", "待确认")):
            lines += [f"- {label}：{value}" for value in segment[key]]
        lines += ["", "采样时间：" + ", ".join(f"{s:.2f}s" for s in segment["sampled_seconds"]), ""]
    lines += ["## 测量与范围", "", "```json", json.dumps(report["timings"], ensure_ascii=False, indent=2), "```", ""]
    lines += [f"- {item}" for item in report["limitations"]]
    return "\n".join(lines) + "\n"


def understand(app, library, source, preset="fast", visual_only=False, transcript=None, refresh=False, audio_source=None):
    started = time.perf_counter()
    context = app.context
    settings = PRESETS[preset]
    path = context.input_path(source)
    if not path.is_file():
        raise FileNotFoundError(path)
    source_stat = path.stat()
    cache = library.root / "cache"
    digest = cached_digest(path, cache)
    info = probe(path)
    if not info["video"]:
        raise ValueError("语义读取需要一个含视频画面的文件")
    if visual_only and transcript:
        raise ValueError("--visual-only 和 --transcript 不能同时使用")
    semantic = app.plugin("semantic")
    identity = semantic.identity()
    transcript_path = context.input_path(transcript) if transcript else None
    audio_path = context.input_path(audio_source) if audio_source else path
    if audio_source and not probe(audio_path)["audio"]:
        raise ValueError("所选配套音频文件没有音轨")
    has_audio = bool(audio_source or info["audio"])
    audio_identity = {"status": "skipped" if visual_only else "absent"}
    speech = None
    if transcript_path:
        audio_identity = {"status": "provided", "sha256": cached_digest(transcript_path, cache),
                          "format": "timed_json" if transcript_path.suffix.lower() == ".json" else "text"}
    elif has_audio and not visual_only:
        speech = app.plugin("speech")
        audio_identity = {"source_sha256": cached_digest(audio_path, cache), **speech.identity()}
    key = fingerprint({"schema_version": REPORT_SCHEMA, "workflow_version": 1,
                       "source": digest, "settings": settings, "semantic": identity, "audio": audio_identity})
    report_path = library.root / "reports" / (key + ".json")
    cached = None if refresh else read_json(report_path)
    if cached and cached.get("schema_version") == REPORT_SCHEMA and cached.get("cache_key") == key:
        if not report_path.with_suffix(".md").exists():
            report_path.with_suffix(".md").write_text(markdown_report(cached), encoding="utf-8")
        cached.update(cache_hit=True, request_wall_s=round(time.perf_counter() - started, 4),
                      requested_source=str(path), report_json=str(report_path),
                      report_markdown=str(report_path.with_suffix(".md")))
        return cached
    timings = {"probe_hash_identity_s": time.perf_counter() - started}
    decode_started = time.perf_counter()
    metadata, frames = sample_video(path, settings["frames"], max_edge=settings["max_edge"], hash_content=False)
    metadata["sha256"] = digest
    duration = metadata["duration_s"]
    timings["sample_decode_resize_s"] = time.perf_counter() - decode_started
    speech_started = time.perf_counter()
    if transcript_path:
        audio = transcript_input(transcript_path, duration)
    elif speech:
        speech_key = fingerprint(audio_identity)
        speech_path = cache / "speech" / (speech_key + ".json")
        audio = None if refresh else read_json(speech_path)
        hit = bool(audio)
        if audio is None:
            audio = speech.transcribe(audio_path)
            write_json(speech_path, audio)
        audio = {**audio, "cache_hit": hit}
    else:
        audio = {**audio_identity, "segments": []}
    timings["speech_wall_s"] = time.perf_counter() - speech_started
    batch_size = settings["batch_frames"]
    batches = [frames[i:i + batch_size] for i in range(0, len(frames), batch_size)]
    segments, metrics = [], []
    for i, batch in enumerate(batches):
        start = 0 if i == 0 else (batches[i - 1][-1][0] + batch[0][0]) / 2
        end = duration if i == len(batches) - 1 else (batch[-1][0] + batches[i + 1][0][0]) / 2
        speech_text = "\n".join(s["text"] for s in audio["segments"] if s["start_s"] < end and s["end_s"] > start)
        result = semantic.describe(batch, speech_text[:12000], settings["max_tokens"])
        description = validate_description(result["description"])
        if len(speech_text) > 12000:
            description["uncertainties"].append("本时间段语音超过上下文预算，只读取前 12000 个字符。")
        segments.append({"start_s": start, "end_s": end, "sampled_seconds": [t for t, _ in batch], **description})
        metrics.append(result.get("metrics", {}))
    timings["semantic_batches"] = metrics
    timings["total_uncached_s"] = time.perf_counter() - started
    timings["processing_to_duration_ratio"] = timings["total_uncached_s"] / duration
    limitations = ["原始媒体未剪辑、拼接或转码；只在内存中解码和缩小采样帧。",
                   "均匀采样用于快速概览，可能漏掉短暂操作；时间段边界由采样位置决定，不是精确事件时间。",
                   "语义是模型候选结论，没有转化为按键计划或已验证游戏经验。"]
    if audio["status"] in {"absent", "skipped"}:
        limitations.append("本次没有识别语音，结论仅来自采样画面；不能据此复述未显示的讲解。")
    elif audio.get("alignment") == "whole_video":
        limitations.append("提供的纯文本没有逐句时间戳，各时间段只能参考全文，不能确定语音发生时间。")
    report = {"schema_version": REPORT_SCHEMA, "cache_key": key, "status": "candidate_understanding",
              "source": str(path), "metadata": metadata, "preset": preset,
              "summary": "\n".join(s["summary"] for s in segments), "segments": segments,
              "audio": audio, "provenance": {"semantic": identity, "audio": audio_identity},
              "timings": timings, "limitations": limitations, "cache_hit": False}
    after = path.stat()
    if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (source_stat.st_size, source_stat.st_mtime_ns, source_stat.st_ctime_ns):
        raise ValueError("理解期间视频发生变化，请读取稳定的原文件")
    write_json(report_path, report)
    report_path.with_suffix(".md").write_text(markdown_report(report), encoding="utf-8")
    report.update(report_json=str(report_path), report_markdown=str(report_path.with_suffix(".md")),
                  request_wall_s=round(time.perf_counter() - started, 4))
    return report
