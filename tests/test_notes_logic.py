import importlib.util
import unittest

from tests.helpers import REPO

spec = importlib.util.spec_from_file_location("notes_main", REPO / "capabilities" / "notes" / "main.py")
notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notes)

BASE = {"me": {"name": "charon"}, "peer": {"name": "pluto", "online": True, "last_seen": None},
        "now": "2026-10-03T14:00:00Z", "latest": {"charon": {}, "pluto": {}}}


def sent(seq, text, origin="pluto"):
    return {"origin": origin, "seq": seq, "type": "notes.sent", "ts": "2026-10-03T13:00:00Z", "v": 1,
            "data": {"text": text}}


class NotesLogicTest(unittest.TestCase):
    def test_too_long_note_is_refused(self):
        out = notes.handle({**BASE, "events": [], "trigger": {"kind": "command", "name": "note", "args": ["x" * 281]}})
        self.assertNotIn("emit", out)
        self.assertIn("at most 280 characters (yours is 281)", out["print"])

    def test_oversized_note_from_the_peer_is_truncated_to_fit_a_bubble(self):
        out = notes.handle({**BASE, "events": [sent(1, "y" * 500)], "trigger": {"kind": "login"}})
        self.assertEqual(len(out["say"][0]["text"]), 280)

    def test_many_unread_are_summarized_but_all_marked_seen(self):
        events = [sent(i, f"note {i}") for i in range(1, 9)]
        out = notes.handle({**BASE, "events": events, "trigger": {"kind": "login"}})
        self.assertEqual(len(out["say"]), 6)
        self.assertIn("and 3 more", out["say"][-1]["text"])
        self.assertEqual(out["emit"][0]["data"]["seqs"], list(range(1, 9)))

    def test_unread_ignores_my_own_notes(self):
        inp = {**BASE, "events": [sent(1, "mine", origin="charon")]}
        self.assertEqual(notes.unread(inp), [])

    def test_malformed_peer_note_does_not_crash(self):
        bad = {**sent(1, "x"), "data": {"text": 42}}
        out = notes.handle({**BASE, "events": [bad], "trigger": {"kind": "login"}})
        self.assertEqual(out["say"][0]["text"], "(empty note)")
