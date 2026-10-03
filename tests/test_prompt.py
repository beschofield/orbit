import tempfile
import unittest
from pathlib import Path

from orbit import prompt
from orbit.store import Store
from tests.helpers import make_cfg


class PromptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.store = Store(self.dir / "orbit.db", "charon")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_segments_follow_prompt_order_then_alphabetical(self):
        for name, text in [("zeta", "Z"), ("notes", "✉ 1"), ("alpha", "A"), ("presence", "♇ pluto: idle")]:
            prompt.set_segment(self.store, name, text)
        built = prompt.build(self.store, ["presence", "notes"], ["alpha", "notes", "presence", "zeta"])
        self.assertEqual(built, "♇ pluto: idle · ✉ 1 · A · Z")

    def test_empty_segment_is_removed(self):
        prompt.set_segment(self.store, "notes", "✉ 1")
        prompt.set_segment(self.store, "notes", "")
        self.assertEqual(prompt.build(self.store, [], ["notes"]), "")

    def test_uninstalled_capability_is_ignored(self):
        prompt.set_segment(self.store, "gone", "old")
        self.assertEqual(prompt.build(self.store, [], ["notes"]), "")

    def test_rebuild_writes_the_file_atomically(self):
        cfg = make_cfg(self.dir)
        prompt.set_segment(self.store, "notes", "✉ 2")
        self.assertEqual(prompt.rebuild(self.store, cfg, ["notes"]), "✉ 2")
        self.assertEqual(cfg.prompt_path.read_text(encoding="utf-8"), "✉ 2")
        self.assertEqual(list(self.dir.glob(".prompt*")), [])
