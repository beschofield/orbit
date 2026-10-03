"""Two daemons on loopback with the real capabilities: sent → received → seen → receipt."""
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO, Machine, wait_for


class NotesRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.charon = Machine(root, "charon", "pluto", 19780, 19781, REPO / "capabilities")
        self.pluto = Machine(root, "pluto", "charon", 19781, 19780, REPO / "capabilities")
        self.charon.start()
        self.pluto.start()

    def tearDown(self):
        self.charon.stop()
        self.pluto.stop()
        self.tmp.cleanup()

    def test_note_receipt_round_trip(self):
        code, out, _ = self.charon.cli("note", "lunch at 1?")
        self.assertEqual(code, 0)
        self.assertIn("Sent!", out)
        self.assertTrue(wait_for(lambda: "✉ 1" in self.pluto.prompt()), self.pluto.prompt())

        code, out, _ = self.pluto.cli("greet")
        self.assertIn("lunch at 1?", out)
        self.assertNotIn("✉", self.pluto.prompt())

        self.assertTrue(wait_for(lambda: "Pluto read your note ♥" in self.charon.cli("greet")[1], timeout=8))
        self.assertNotIn("read your note", self.charon.cli("greet")[1])
