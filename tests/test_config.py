import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orbit import config
from orbit.config import ConfigError
from orbit.log import log


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_fill_in(self):
        config.write(self.dir, {"me": "charon", "peer": "pluto"})
        cfg = config.load(self.dir)
        self.assertEqual(cfg.port, 1978)
        self.assertEqual(cfg.peer_host, "pluto")
        self.assertEqual(cfg.peer_url, "http://pluto:1978")
        self.assertEqual(cfg.prompt_order, ["presence", "notes"])
        self.assertEqual(cfg.capabilities_dir, config.REPO_ROOT / "capabilities")
        self.assertIsNone(cfg.bind)
        self.assertEqual(cfg.dev_allow_ips, [])
        self.assertEqual(cfg.db_path, self.dir / "orbit.db")
        self.assertEqual(cfg.prompt_path, self.dir / "prompt")

    def test_missing_file_says_how_to_fix(self):
        with self.assertRaises(ConfigError) as ctx:
            config.load(self.dir)
        self.assertIn("orbit init", str(ctx.exception))

    def test_invalid_json_names_the_line(self):
        (self.dir / "config.json").write_text('{"me": "charon",\n "peer": }')
        with self.assertRaises(ConfigError) as ctx:
            config.load(self.dir)
        self.assertIn("line 2", str(ctx.exception))

    def test_unknown_character_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            config.from_dict({"me": "earth", "peer": "pluto"}, self.dir, "cfg")
        self.assertIn('"me" must be "pluto" or "charon"', str(ctx.exception))

    def test_me_and_peer_must_differ(self):
        with self.assertRaises(ConfigError) as ctx:
            config.from_dict({"me": "pluto", "peer": "pluto"}, self.dir, "cfg")
        self.assertIn("must be different", str(ctx.exception))

    def test_wrong_type_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            config.from_dict({"me": "charon", "peer": "pluto", "port": "1978"}, self.dir, "cfg")
        self.assertIn('"port" must be a whole number', str(ctx.exception))

    def test_peer_url_trailing_slash_removed(self):
        cfg = config.from_dict({"me": "charon", "peer": "pluto", "peer_url": "http://x:1/"}, self.dir, "cfg")
        self.assertEqual(cfg.peer_url, "http://x:1")

    def test_data_dir_honours_env(self):
        with mock.patch.dict(os.environ, {"ORBIT_DIR": str(self.dir)}):
            self.assertEqual(config.data_dir(), self.dir)

    def test_log_appends_and_never_raises(self):
        log(self.dir, "notes", "first")
        log(self.dir, "notes", "second")
        lines = (self.dir / "logs" / "notes.log").read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].endswith(" second"))
        log(Path("/proc/not/writable"), "x", "ignored")  # must not raise
