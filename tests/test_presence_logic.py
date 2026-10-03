import importlib.util
import unittest

from tests.helpers import REPO

spec = importlib.util.spec_from_file_location("presence_main", REPO / "capabilities" / "presence" / "main.py")
presence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(presence)

WHO = """\
becca    pts/0        2026-10-03 13:58   .          1234 (100.69.87.124)
becca    pts/1        2026-10-03 09:00 01:20        2345 (100.69.87.124)
gabby    pts/2        2026-10-03 12:00 00:02        3456 (100.69.87.124)
"""


def inp(trigger="tick", mine=None, theirs=None, online=True):
    def status(origin, data):
        return {"origin": origin, "seq": 1, "type": "presence.status", "ts": "2026-10-03T13:00:00Z", "v": 1, "data": data}
    return {"trigger": {"kind": trigger}, "me": {"name": "charon"},
            "peer": {"name": "pluto", "online": online, "last_seen": None},
            "latest": {"charon": {"presence.status": status("charon", mine)} if mine else {},
                       "pluto": {"presence.status": status("pluto", theirs)} if theirs else {}}}


class PresenceLogicTest(unittest.TestCase):
    def test_parse_idle(self):
        self.assertEqual(presence.parse_idle("."), 0)
        self.assertEqual(presence.parse_idle("01:20"), 80)
        self.assertEqual(presence.parse_idle("old"), 1440)
        self.assertIsNone(presence.parse_idle("?"))

    def test_idle_minutes_takes_the_freshest_session(self):
        self.assertEqual(presence.idle_minutes(WHO, "becca"), 0)
        self.assertEqual(presence.idle_minutes(WHO, "gabby"), 2)
        self.assertIsNone(presence.idle_minutes(WHO, "nobody"))

    def test_state_thresholds(self):
        self.assertEqual([presence.state_for(m) for m in (0, 4, 5, 59, 60, None)],
                         ["active", "active", "idle", "idle", "away", "away"])

    def test_tick_emits_only_on_change(self):
        unchanged = presence.tick(inp(mine={"state": "active", "manual": False}), who_output=WHO, user="becca")
        self.assertNotIn("emit", unchanged)
        self.assertIn("prompt", unchanged)
        changed = presence.tick(inp(mine={"state": "idle", "manual": False}), who_output=WHO, user="becca")
        self.assertEqual(changed["emit"][0]["data"], {"state": "active", "manual": False})

    def test_control_characters_from_the_peer_are_dropped(self):
        text = presence.prompt_text(inp(theirs={"state": "away", "message": "\x1b[2Jgym"}))
        self.assertNotIn("\x1b", text)
        self.assertTrue(text.isprintable())

    def test_long_messages_are_truncated_to_40(self):
        text = presence.prompt_text(inp(theirs={"state": "away", "message": "m" * 80}))
        self.assertEqual(len(text), 40)
        self.assertTrue(text.endswith("…"))
