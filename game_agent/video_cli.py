"""Stage-one CLI stays separate from the action execution runtime."""

from .video_contracts import CATEGORIES, PRESETS
from .video_library import VideoLibrary
from .video_workflow import understand

COMMANDS = {"download", "add-video", "videos", "classify", "understand"}


def add_commands(commands):
    download = commands.add_parser("download", help="you-get 下载原视频，默认分类为视频教程")
    download.add_argument("source", help="视频网页或媒体 URL")
    download.add_argument("--category", choices=CATEGORIES)
    local = commands.add_parser("add-video", help="复制已有原视频到本项目并分类")
    local.add_argument("source")
    local.add_argument("--category", choices=CATEGORIES)
    commands.add_parser("videos", help="列出原视频及分类")
    classify = commands.add_parser("classify", help="只更新分类，不移动或修改原视频")
    classify.add_argument("id")
    classify.add_argument("category", choices=CATEGORIES)
    read = commands.add_parser("understand", help="输出视频语义和耗时，不生成游戏操作")
    read.add_argument("sources", nargs="+", help="视频编号或本地视频路径；批量读取复用模型")
    read.add_argument("--preset", choices=PRESETS, default="fast")
    read.add_argument("--refresh", action="store_true", help="忽略语义/语音缓存重新测量")
    audio = read.add_mutually_exclusive_group()
    audio.add_argument("--visual-only", action="store_true", help="只读画面，明确跳过语音")
    audio.add_argument("--transcript", help="提供 UTF-8 文本或带 start_s/end_s/text 的 JSON 数组")
    read.add_argument("--audio", help="手动指定与单个视频对齐的独立音频流")


def handle(args, app):
    with VideoLibrary(app.context) as library:
        if args.command == "download":
            return library.add(args.source, app.plugin("downloader"), args.category)
        if args.command == "add-video":
            return library.add(args.source, category=args.category)
        if args.command == "videos":
            return library.list()
        if args.command == "classify":
            return library.classify(args.id, args.category)
        if len(args.sources) != 1 and (args.audio or args.transcript):
            raise ValueError("手动音频/字幕需要一次指定一个视频")
        results = []
        for source in args.sources:
            path = app.context.input_path(source)
            asset = None
            if path.is_file():
                media = [{"path": str(path), "video": True, "audio": False}]
            else:
                asset = library.get(source)
                media = asset["media"]
            videos = [m for m in media if m["video"]]
            audios = [m for m in media if m["audio"] and not m["video"]]
            if len(videos) > 1 and (args.audio or args.transcript):
                raise ValueError("多视频分段需按文件路径逐段指定音频/字幕")
            for item in videos:
                # One video + one audio is the common unmerged DASH layout.
                # Multiple segments are described individually, never silently concatenated.
                audio_source = args.audio
                if len(videos) == 1 and len(audios) == 1 and not item["audio"]:
                    audio_source = audio_source or audios[0]["path"]
                report = understand(app, library, item["path"], args.preset,
                                    args.visual_only, args.transcript, args.refresh, audio_source)
                if asset:
                    report["asset"] = {k: asset[k] for k in ("id", "category", "category_label")}
                    report["asset"]["video_parts"] = len(videos)
                results.append(report)
        return results[0] if len(results) == 1 else results
