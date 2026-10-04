import json
import tempfile
import unittest
from pathlib import Path

from orbit import contract
from orbit.contract import ContractError
from tests.helpers import write_cap

GOOD = dict(
    commands=[{"name": "note", "usage": "note <text>", "help": "Send a note."}],
    triggers=["login", "received"],
    event_types={"notes.sent": {"keep": "log"}, "notes.seen": {"keep": "log"}},
    receives=["notes.sent"],
)


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def problems(self, folder: str = "notes", **overrides) -> list[str]:
        d = write_cap(self.root, folder, "#!/bin/sh\necho '{}'\n", **{**GOOD, **overrides})
        try:
            contract.parse_manifest(d / "manifest.json")
        except ContractError as e:
            return e.problems
        return []

    def test_good_manifest_parses(self):
        d = write_cap(self.root, "notes", "#!/bin/sh\n", **GOOD)
        m = contract.parse_manifest(d / "manifest.json")
        self.assertEqual(m.name, "notes")
        self.assertEqual(m.run, d / "main.py")
        self.assertEqual([c.name for c in m.commands], ["note"])
        self.assertEqual(m.event_types, {"notes.sent": "log", "notes.seen": "log"})
        self.assertEqual(m.receives, ("notes.sent",))
        self.assertIsNone(m.tick_seconds)
        self.assertEqual(m.dir, d)

    def test_event_type_prefix_error_says_how_to_rename(self):
        probs = self.problems(event_types={"sent": {"keep": "log"}})
        self.assertIn('manifest.json: event_types."sent": must start with "notes." — rename to "notes.sent"', probs[0])

    def test_folder_must_match_name(self):
        probs = self.problems(name="memo")
        self.assertTrue(any('is "memo" but the folder is "notes"' in p for p in probs), probs)

    def test_run_must_exist(self):
        self.assertTrue(any("does not exist" in p for p in self.problems(run="missing.py")))

    def test_run_must_be_executable(self):
        d = write_cap(self.root, "notes", "#!/bin/sh\n", **GOOD)
        (d / "main.py").chmod(0o644)
        with self.assertRaises(ContractError) as ctx:
            contract.parse_manifest(d / "manifest.json")
        self.assertIn("chmod +x", ctx.exception.problems[0])

    def test_reserved_command_rejected(self):
        probs = self.problems(commands=[{"name": "doctor", "usage": "doctor", "help": "x"}])
        self.assertTrue(any('"doctor" is reserved' in p for p in probs), probs)

    def test_tick_needs_tick_seconds_of_at_least_10(self):
        self.assertTrue(any("tick_seconds" in p for p in self.problems(triggers=["tick"], receives=[])))
        self.assertTrue(any("tick_seconds" in p for p in self.problems(triggers=["tick"], receives=[], tick_seconds=5)))
        self.assertEqual(self.problems(triggers=["tick"], receives=[], tick_seconds=60), [])

    def test_command_trigger_is_implied(self):
        self.assertTrue(any('"command" is implied' in p for p in self.problems(triggers=["command", "received"])))

    def test_received_and_receives_go_together(self):
        self.assertTrue(any("receives" in p for p in self.problems(triggers=["received"], receives=[])))
        self.assertTrue(any('lacks "received"' in p for p in self.problems(triggers=[], receives=["notes.sent"])))

    def test_bad_keep_rejected(self):
        probs = self.problems(event_types={"notes.sent": {"keep": "forever"}})
        self.assertTrue(any('must be "log" or "latest"' in p for p in probs), probs)

    def test_all_problems_reported_together(self):
        self.assertGreaterEqual(len(self.problems(description="", contract=2)), 2)

    def test_invalid_json_manifest(self):
        d = self.root / "notes"
        d.mkdir()
        (d / "manifest.json").write_text("{nope")
        with self.assertRaises(ContractError) as ctx:
            contract.parse_manifest(d / "manifest.json")
        self.assertIn("invalid JSON", ctx.exception.problems[0])


class OutputTest(unittest.TestCase):
    def setUp(self):
        data = {"name": "notes", "description": "d", "contract": 1, "run": "main.py", **GOOD}
        self.m = contract.manifest_from_dict(data, Path("/x/notes"), "manifest", check_files=False)

    def problems(self, obj) -> list[str]:
        with self.assertRaises(ContractError) as ctx:
            contract.parse_output(json.dumps(obj), self.m)
        return ctx.exception.problems

    def test_full_output(self):
        out = contract.parse_output(json.dumps({
            "say": [{"who": "pluto", "mood": "love", "text": "hi ♥"}],
            "emit": [{"type": "notes.seen", "data": {"seqs": [1]}}],
            "prompt": "✉ 1", "print": "ok"}), self.m)
        self.assertEqual(out.say[0].text, "hi ♥")
        self.assertEqual(out.emit[0].v, 1)
        self.assertEqual(out.prompt, "✉ 1")
        self.assertEqual(out.print_text, "ok")

    def test_empty_stdout_means_do_nothing(self):
        self.assertEqual(contract.parse_output("  \n", self.m), contract.Output())

    def test_debug_print_on_stdout_says_use_stderr(self):  # Review Focus #5
        with self.assertRaises(ContractError) as ctx:
            contract.parse_output('debug: here\n{"say": []}', self.m)
        self.assertIn("send debug output to stderr", ctx.exception.problems[0])

    def test_emit_must_be_declared(self):
        probs = self.problems({"emit": [{"type": "notes.deleted", "data": {}}]})
        self.assertIn('emit[0].type: "notes.deleted" is not declared in manifest.json event_types — add it there', probs[0])

    def test_bad_who_and_mood(self):
        probs = self.problems({"say": [{"who": "earth", "mood": "angry", "text": "x"}]})
        self.assertEqual(len(probs), 2)

    def test_say_text_limit(self):
        self.assertIn("280", self.problems({"say": [{"who": "pluto", "mood": "happy", "text": "x" * 281}]})[0])

    def test_prompt_limits(self):
        self.assertIn("40", self.problems({"prompt": "x" * 41})[0])
        self.assertIn("control characters", self.problems({"prompt": "a\nb"})[0])
        self.assertIn("control characters", self.problems({"prompt": "\x1b[31mred"})[0])

    def test_unknown_key(self):
        self.assertIn("allowed keys", self.problems({"says": []})[0])

    def test_data_size_limit(self):
        self.assertIn("16384", self.problems({"emit": [{"type": "notes.sent", "data": {"t": "x" * 17000}}]})[0])

    def test_non_string_emit_type_is_a_contract_error(self):
        self.assertIn("is not declared", self.problems({"emit": [{"type": ["x"], "data": {}}]})[0])

    def test_look_defaults_to_forward(self):
        out = contract.parse_output('{"say": [{"who": "pluto", "mood": "happy", "text": "hi"}]}', self.m)
        self.assertEqual(out.say[0].look, "forward")

    def test_look_side_is_accepted(self):
        out = contract.parse_output(json.dumps(
            {"say": [{"who": "pluto", "mood": "love", "look": "side", "text": "hi"}]}), self.m)
        self.assertEqual(out.say[0].look, "side")

    def test_bad_look_says_how_to_fix(self):  # Review Focus #1, #2
        for look in ("Side", "left", None, ["side"], {"look": "side"}):
            with self.subTest(look=look):
                probs = self.problems({"say": [{"who": "pluto", "mood": "happy", "look": look, "text": "hi"}]})
                self.assertEqual(len(probs), 1, probs)
                self.assertIn('say[0].look', probs[0])
                self.assertIn('must be "forward" or "side" (leave it out for "forward")', probs[0])

    def test_output_to_dict_leaves_out_forward_look(self):
        out = contract.parse_output(json.dumps({"say": [
            {"who": "charon", "mood": "happy", "text": "a"},
            {"who": "pluto", "mood": "love", "look": "side", "text": "b"}]}), self.m)
        self.assertEqual(contract.output_to_dict(out)["say"], [
            {"who": "charon", "mood": "happy", "text": "a"},
            {"who": "pluto", "mood": "love", "look": "side", "text": "b"}])

    def test_output_to_dict(self):
        out = contract.parse_output('{"emit": [{"type": "notes.sent", "data": {"text": "a"}}]}', self.m)
        self.assertEqual(contract.output_to_dict(out), {
            "say": [], "emit": [{"type": "notes.sent", "data": {"text": "a"}, "v": 1}],
            "prompt": None, "print": None})
