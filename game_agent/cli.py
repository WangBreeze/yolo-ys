"""Local inference and execution; only explicit download/setup commands use the network."""

import argparse
import importlib.util
import json
import shutil
import sys
from dataclasses import asdict

from .config import load_config
from .contracts import canonical
from .registry import registry_for
from .runtime import Application
from .video_cli import COMMANDS as VIDEO_COMMANDS, add_commands, handle as handle_video
from .training_cli import COMMANDS as TRAINING_COMMANDS, add_commands as add_training_commands, handle as handle_training


def doctor(context, registry):
    deps = {"yolo.perception": ["cv2", "torch", "ultralytics"],
            "video.capture": ["cv2"], "hyprland.capture": ["cv2"],
            "uinput.controller": ["evdev"],
            "windows.capture": ["mss", "numpy"],
            "yolo.detector-trainer": ["cv2", "torch", "ultralytics"],
            "qwen-video.tutorial": ["cv2", "torch", "transformers", "PIL"],
            "you-get.downloader": ["you_get"],
            "qwen3.semantic": ["cv2", "torch", "transformers", "PIL"],
            "faster-whisper.speech": ["faster_whisper"]}
    issues = []
    for role, selection in context.config["plugins"].items():
        plugin_id = selection["use"]
        if plugin_id not in registry.specs or registry.specs[plugin_id].role != role:
            issues.append(f"invalid {role} plugin: {plugin_id}")
            continue
        for dep in deps.get(plugin_id, []):
            if importlib.util.find_spec(dep) is None:
                issues.append(f"{plugin_id}: missing Python dependency {dep}")
        opts = selection.get("options", {})
        if role in {"downloader", "semantic"} and not shutil.which("ffprobe"):
            issues.append("video library: missing executable ffprobe")
        for name in ("weights", "model", "path", "transcript", "whisper_weights"):
            if role != "memory" and opts.get(name) and not context.input_path(opts[name]).exists():
                issues.append(f"{plugin_id}: missing local {name}: {opts[name]}")
        if opts.get("model") and plugin_id in {"qwen3.semantic", "faster-whisper.speech"}:
            model_path = context.input_path(opts["model"])
            ready = (any(model_path.glob("*.safetensors")) if plugin_id == "qwen3.semantic"
                     else (model_path / "model.bin").is_file())
            if not ready:
                issues.append(f"{plugin_id}: model weights are not ready; run tools/fetch-video-models.py")
        if plugin_id in ("hyprland.capture", "uinput.controller"):
            if sys.platform != "linux":
                issues.append(f"{plugin_id}: requires Linux")
            if not opts.get("window_class"):
                issues.append(f"{plugin_id}: window_class is required")
            for executable in (["hyprctl", "grim"] if role == "capture" else ["hyprctl"]):
                if not shutil.which(executable):
                    issues.append(f"{plugin_id}: missing executable {executable}")
        if plugin_id in ("windows.capture", "windows.controller"):
            if sys.platform != "win32":
                issues.append(f"{plugin_id}: requires Windows 10/11; use offline-training.toml on Linux")
            if not opts.get("window_class") and not opts.get("window_title"):
                issues.append(f"{plugin_id}: exact window_class or window_title is required")
    if context.mode == "live" and any(str(v).startswith("configure-") for v in context.config["game"].values()):
        issues.append("replace the example game/version/profile with actual game information")
    return {"ok": not issues, "root": str(context.root), "game": asdict(context.game),
            "mode": context.mode, "platform": sys.platform, "issues": issues}


def main(argv=None):
    parser = argparse.ArgumentParser(description="本地插件式游戏代理")
    parser.add_argument("--config", help="默认使用 demo.toml；视频命令使用 video.toml")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="运行动作驱动的模拟游戏")
    commands.add_parser("plugins", help="列出可选插件，不加载模型")
    commands.add_parser("doctor", help="检查配置和依赖，不操作游戏")
    ingest = commands.add_parser("ingest", help="理解教程，保存候选计划")
    ingest.add_argument("source")
    ingest.add_argument("--output", help="可选：保存解析后的计划 JSON")
    run = commands.add_parser("run", help="执行教程计划")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--plan")
    source.add_argument("--plan-id")
    run.add_argument("--live", action="store_true")
    recall = commands.add_parser("recall", help="检索当前游戏的本地记忆")
    recall.add_argument("query", nargs="?", default="")
    train = commands.add_parser("train", help="从成功轨迹训练动作经验表")
    train.add_argument("--output", default="memory/models/action-memory.json")
    export = commands.add_parser("export", help="导出完整运行日志或已验证训练样本")
    export.add_argument("--output", required=True)
    export.add_argument("--run-id")
    inspect = commands.add_parser("inspect-video", help="读取本地视频并输出采样元信息")
    inspect.add_argument("source")
    inspect.add_argument("--frames", type=int, default=16)
    windows = commands.add_parser("windows-info", help="只读获取 Windows 前台窗口信息，可保存客户区截图")
    windows.add_argument("--delay", type=int, default=5, help="切到游戏的等待秒数，0–30")
    windows.add_argument("--output", help="可选：保存 PNG 截图到本项目")
    add_commands(commands)
    add_training_commands(commands)
    args = parser.parse_args(argv)
    try:
        default_config = ("configs/offline-training.toml" if args.command in TRAINING_COMMANDS else
                          "configs/video.toml" if args.command in VIDEO_COMMANDS else "configs/demo.toml")
        context = load_config(args.config or default_config)
        registry = registry_for(context)
        if args.command == "plugins":
            result = [asdict(v) for v in registry.specs.values()]
        elif args.command == "doctor":
            result = doctor(context, registry)
            print(canonical(result))
            return 0 if result["ok"] else 1
        elif args.command == "inspect-video":
            from .media import sample_video
            result, _ = sample_video(context.input_path(args.source), args.frames)
        elif args.command == "windows-info":
            from .plugins.windows import Win32Desktop, WindowsCapture
            from time import sleep
            desktop = Win32Desktop()
            if not 0 <= args.delay <= 30:
                raise ValueError("--delay must be in [0, 30]")
            sleep(args.delay)
            result = desktop.foreground()
            if args.output:
                import cv2
                options = context.config["plugins"]["capture"].get("options", {})
                if not options.get("window_class") and not options.get("window_title"):
                    options = {"window_class": result["class"], "window_title": result["title"]}
                capture = WindowsCapture(context, options)
                try:
                    frame = capture.capture()
                    if frame.window_id != result["id"]:
                        raise ValueError("foreground changed before screenshot")
                    ok, encoded = cv2.imencode(".png", frame.pixels)
                    if not ok:
                        raise ValueError("screenshot encoding failed")
                    path = context.output_path(args.output)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(encoded.tobytes())
                    result["screenshot"] = str(path)
                finally:
                    capture.close()
        else:
            with Application(context, registry) as app:
                if args.command in VIDEO_COMMANDS:
                    result = handle_video(args, app)
                elif args.command in TRAINING_COMMANDS:
                    result = handle_training(args, app)
                elif args.command == "ingest":
                    plan_id = app.ingest(args.source)
                    plan = app.plugin("memory").load_plan(plan_id, context.game)
                    result = {"plan_id": plan_id, "status": "candidate", "title": plan.title}
                    if args.output:
                        path = context.output_path(args.output)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(canonical(asdict(plan)) + "\n", encoding="utf-8")
                elif args.command in ("run", "demo"):
                    if args.command == "demo":
                        if context.mode != "simulation" or context.game.id != "demo-shop":
                            raise ValueError("demo needs a demo-shop simulation profile")
                        plan_id = app.ingest("examples/shop-tutorial.json")
                    elif args.plan:
                        # run --plan reads a validated plan, independently of the tutorial provider.
                        from .contracts import Plan
                        plan = Plan.from_dict(json.loads(context.input_path(args.plan).read_text(encoding="utf-8")))
                        plan_id = app.plugin("memory").remember(plan)
                    else:
                        plan_id = args.plan_id
                    plan = app.plugin("memory").load_plan(plan_id, context.game)
                    result = app.run(plan, live=getattr(args, "live", False))
                    print(canonical(result))
                    return 0 if result["status"] in ("success", "dry-run") else 1
                elif args.command == "recall":
                    result = app.plugin("memory").recall(args.query, context.game, context.mode)
                elif args.command == "train":
                    samples = app.plugin("memory").examples(context.game, context.mode)
                    result = app.plugin("learner").train(samples, args.output)
                elif args.command == "export":
                    path = context.output_path(args.output)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    memory = app.plugin("memory")
                    if args.run_id:
                        memory.export_run(args.run_id, path)
                    else:
                        samples = memory.examples(context.game, context.mode)
                        path.write_text("".join(canonical(row) + "\n" for row in samples), encoding="utf-8")
                    result = {"path": str(path)}
        print(canonical(result))
        return 0
    except (ValueError, KeyError, TypeError, OSError, ImportError, RuntimeError) as exc:
        print(f"game-agent: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
