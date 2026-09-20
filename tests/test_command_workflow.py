import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from game_agent.command_contracts import CommandBundle, CommandEvidence, SemanticCommand
from game_agent.command_workflow import extract_commands, load_lexicon, read_bundle, write_bundle
from game_agent.contracts import Game


ROOT = Path(__file__).resolve().parents[1]
LEXICON = ROOT / "configs/genshin-command-lexicon.json"


def sample_report():
    return {
        "schema_version": 1,
        "status": "candidate_understanding",
        "source": "/local/tutorial.mp4",
        "cache_key": "report-key",
        "metadata": {"duration_s": 10.0, "sha256": "source-sha"},
        "audio": {"segments": [
            {"start_s": 0.5, "end_s": 2.0,
             "text": "打开地图，传送到地图右上角的传统帽点"},
            {"start_s": 2.1, "end_s": 4.0,
             "text": "清怪以后开启保险，再拿一下神头"}
        ]},
        "segments": [{
            "start_s": 0.0, "end_s": 5.0, "summary": "地图传送与收集",
            "observations": [], "operation_intents": [],
            "uncertainties": ["目标位置需要画面确认"]
        }],
        "provenance": {
            "semantic": {"plugin": "qwen3.semantic", "version": "1.0.4"},
            "audio": {"plugin": "faster-whisper.speech", "version": "1.0.0"}
        }
    }


class CommandWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.lexicon = load_lexicon(LEXICON)
        self.game = Game("genshin", "tutorial-build-unknown", "voice-command-v1")

    def test_reference_lexicon_has_versioned_bettergi_sources(self):
        reference = self.lexicon["reference"]
        self.assertEqual(reference["project"], "BetterGI")
        self.assertEqual(len(reference["commit"]), 40)
        self.assertIn("teleport", self.lexicon["commands"])
        self.assertIn("fight_until_clear", self.lexicon["commands"])
        self.assertIn("grab_four_leaf_sigil", self.lexicon["commands"])

    def test_extract_preserves_original_speech_and_records_corrections(self):
        bundle = extract_commands(sample_report(), self.lexicon, self.game)
        names = [command.name for command in bundle.commands]
        self.assertIn("open_map", names)
        self.assertIn("teleport", names)
        self.assertIn("fight_until_clear", names)
        self.assertIn("open_chest", names)
        self.assertIn("collect", names)
        chest = next(command for command in bundle.commands if command.name == "open_chest")
        self.assertIn("保险", chest.evidence.transcript)
        self.assertIn("保险→宝箱", chest.evidence.corrections)
        self.assertIn("神头→神瞳", chest.evidence.corrections)
        teleport = next(command for command in bundle.commands if command.name == "teleport")
        self.assertEqual(teleport.params["direction"], "northeast")
        self.assertIn("teleport_waypoint", teleport.params["targets"])
        self.assertEqual(teleport.status, "candidate")

    def test_semantic_commands_reject_raw_input_parameters(self):
        evidence = CommandEvidence(0, 1, "向前走")
        with self.assertRaisesRegex(ValueError, "raw input params"):
            SemanticCommand("bad", "move_toward", {"key": "W"}, evidence)
        with self.assertRaisesRegex(ValueError, "raw input params"):
            SemanticCommand("bad", "move_toward", {"x": 0.5, "y": 0.5}, evidence)

    def test_bundle_round_trip_and_static_check(self):
        bundle = extract_commands(sample_report(), self.lexicon, self.game)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "commands.json"
            write_bundle(path, bundle)
            loaded, result = read_bundle(path, self.lexicon)
        self.assertEqual(asdict(loaded), asdict(bundle))
        self.assertTrue(result["ok"])
        self.assertEqual(result["commands"], len(bundle.commands))

    def test_unknown_command_and_out_of_range_evidence_are_rejected(self):
        bundle = extract_commands(sample_report(), self.lexicon, self.game)
        data = asdict(bundle)
        data["commands"][0]["name"] = "invented_key_sequence"
        path_data = json.loads(json.dumps(data))
        unknown = CommandBundle.from_dict(path_data)
        from game_agent.command_workflow import validate_against_lexicon
        with self.assertRaisesRegex(ValueError, "unknown semantic command"):
            validate_against_lexicon(unknown, self.lexicon)
        data = asdict(bundle)
        data["commands"][0]["evidence"]["end_s"] = 11.0
        with self.assertRaisesRegex(ValueError, "exceeds source duration"):
            CommandBundle.from_dict(json.loads(json.dumps(data)))


if __name__ == "__main__":
    unittest.main()
