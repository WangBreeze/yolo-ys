"""CLI for Linux/Windows offline visual training, separate from live action traces."""

from . import training_data

COMMANDS = {"prepare-dataset", "build-dataset", "check-dataset", "train-detector"}


def add_commands(commands):
    prepare = commands.add_parser("prepare-dataset", help="从视频生成待标注视觉数据，不生成键鼠标签")
    prepare.add_argument("sources", nargs="+")
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--classes", nargs="+", required=True)
    prepare.add_argument("--group", required=True, help="同一游戏录制场次使用同一组名")
    prepare.add_argument("--split", choices=sorted(training_data.SPLITS), default="unassigned")
    prepare.add_argument("--frames", type=int, default=32)
    build = commands.add_parser("build-dataset", help="检查已复核标注并导出可迁移的 YOLO 数据集")
    build.add_argument("manifests", nargs="+")
    build.add_argument("--output", required=True)
    check = commands.add_parser("check-dataset", help="检查训练数据完整性，不加载模型")
    check.add_argument("source")
    train = commands.add_parser("train-detector", help="用已复核的离线数据训练视觉检测模型")
    train.add_argument("source")
    train.add_argument("--output", required=True)


def handle(args, app):
    if args.command == "prepare-dataset":
        return training_data.prepare(app.context, args.sources, args.output, args.classes,
                                     args.group, args.split, args.frames)
    if args.command == "build-dataset":
        return training_data.build(app.context, args.manifests, args.output)
    if args.command == "check-dataset":
        path, data = training_data.validate_dataset(app.context, args.source)
        return {"ok": True, "path": str(path), "counts": data["counts"], "classes": data["classes"]}
    return app.plugin("detector_trainer").train(args.source, args.output)
