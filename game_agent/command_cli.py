"""CLI commands for the reviewable tutorial-speech command stage."""

from collections import Counter
from dataclasses import asdict
import json

from .command_workflow import extract_commands, load_lexicon, read_bundle, write_bundle

COMMANDS = {"extract-commands", "check-commands", "list-commands"}
DEFAULT_LEXICON = "configs/genshin-command-lexicon.json"


def add_commands(commands):
    extract = commands.add_parser("extract-commands", help="从第一阶段报告提取候选语义命令")
    extract.add_argument("report", help="第一阶段 report JSON")
    extract.add_argument("--lexicon", default=DEFAULT_LEXICON)
    extract.add_argument("--output", help="默认写入 memory/commands/<报告缓存键>.json")
    check = commands.add_parser("check-commands", help="静态校验候选语义命令")
    check.add_argument("source", help="候选命令 JSON")
    check.add_argument("--lexicon", default=DEFAULT_LEXICON)
    listing = commands.add_parser("list-commands", help="列出原神语义命令词典")
    listing.add_argument("--lexicon", default=DEFAULT_LEXICON)


def handle(args, context):
    lexicon_path = context.input_path(args.lexicon)
    lexicon = load_lexicon(lexicon_path)
    if args.command == "list-commands":
        return {"lexicon": {"id": lexicon["id"], "version": lexicon["version"]},
                "commands": [{"name": name, "category": spec["category"],
                              "capability": spec["capability"]}
                             for name, spec in lexicon["commands"].items()]}
    if args.command == "check-commands":
        _, result = read_bundle(context.input_path(args.source), lexicon)
        result["path"] = str(context.input_path(args.source))
        return result
    report = json.loads(context.input_path(args.report).read_text(encoding="utf-8"))
    bundle = extract_commands(report, lexicon, context.game)
    output = args.output or f"memory/commands/{report.get('cache_key') or bundle.id}.json"
    path = context.output_path(output)
    write_bundle(path, bundle)
    counts = Counter(command.name for command in bundle.commands)
    corrections = sum(bool(command.evidence.corrections) for command in bundle.commands)
    return {"path": str(path), "bundle_id": bundle.id, "status": bundle.status,
            "commands": len(bundle.commands), "commands_with_corrections": corrections,
            "by_name": dict(sorted(counts.items())),
            "lexicon": asdict(bundle)["lexicon"]}
