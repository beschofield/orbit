import importlib.util
import os
import tempfile
import unittest

from tests.helpers import REPO

spec = importlib.util.spec_from_file_location("presence_main", REPO / "capabilities" / "presence" / "main.py")
presence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(presence)

NOW = 1_790_000_000.0



def inp(trigger="tick", mine=None, theirs=None, online=True):
    def status(origin, data):
        return {"origin": origin, "seq": 1, "type": "presence.status", "ts": "2026-10-03T13:00:00Z", "v": 1, "data": data}
    return {"trigger": {"kind": trigger}, "me": {"name": "charon"},
            "peer": {"name": "pluto", "online": online, "last_seen": None},
            "latest": {"charon": {"presence.status": status("charon", mine)} if mine else {},
                       "pluto": {"presence.status": status("pluto", theirs)} if theirs else {}}}


class PresenceLogicTest(unittest.TestCase):
    def make_pts(self, ages: dict) -> str:
        """A fake /dev/pts: one file per tty, its atime set `ages[name]` seconds before NOW."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name, age in ages.items():
            path = os.path.join(tmp.name, name)
            open(path, "w").close()
            os.utime(path, (NOW - age, NOW - age))
        return tmp.name

    def test_idle_minutes_takes_the_freshest_tty(self):
        pts = self.make_pts({"0": 20, "1": 80 * 60, "ptmx": 0})
        self.assertEqual(presence.idle_minutes(pts, uid=os.getuid(), now=NOW), 0)
        pts = self.make_pts({"3": 150, "4": 3 * 3600})
        self.assertEqual(presence.idle_minutes(pts, uid=os.getuid(), now=NOW), 2)

    def test_idle_minutes_ignores_ptmx_and_other_users(self):
        pts = self.make_pts({"ptmx": 0, "0": 30})
        self.assertIsNone(presence.idle_minutes(pts, uid=os.getuid() + 1, now=NOW))
        self.assertIsNone(presence.idle_minutes(self.make_pts({"ptmx": 0}), uid=os.getuid(), now=NOW))

    def test_idle_minutes_without_a_pts_dir_is_none(self):
        self.assertIsNone(presence.idle_minutes("/nonexistent/pts", uid=os.getuid(), now=NOW))

    def test_state_thresholds(self):
        self.assertEqual([presence.state_for(m) for m in (0, 4, 5, 59, 60, None)],
                         ["active", "active", "idle", "idle", "away", "away"])

    def test_tick_emits_only_on_change(self):
        unchanged = presence.tick(inp(mine={"state": "active", "manual": False}), idle=0)
        self.assertNotIn("emit", unchanged)
        self.assertIn("prompt", unchanged)
        changed = presence.tick(inp(mine={"state": "idle", "manual": False}), idle=0)
        self.assertEqual(changed["emit"][0]["data"], {"state": "active", "manual": False})

    def test_control_characters_from_the_peer_are_dropped(self):
        text = presence.prompt_text(inp(theirs={"state": "away", "message": "\x1b[2Jgym"}))
        self.assertNotIn("\x1b", text)
        self.assertTrue(text.isprintable())

    def test_long_messages_are_truncated_to_40(self):
        text = presence.prompt_text(inp(theirs={"state": "away", "message": "m" * 80}))
        self.assertEqual(len(text), 40)
        self.assertTrue(text.endswith("…"))
