import io
import os
import sys
import tempfile
import time
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock
import unittest
from pathlib import Path

from orbit import cli, config
from orbit.store import Store
from tests.helpers import py, run_cli, write_cap

HELLO = py('''
name = " ".join(inp["trigger"]["args"]) or "friend"
print(json.dumps({"print": f"hello, {name}!", "say": [{"who": "charon", "mood": "happy", "text": "hi " + name}]}))
''')
HELLO_CMD = [{"name": "hello", "usage": "hello [name]", "help": "say hello"}]


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.caps = self.root / "caps"
        self.caps.mkdir()
        self.data = self.root / "data"
        config.write(self.data, {"me": "charon", "peer": "pluto", "capabilities_dir": str(self.caps),
                                 "peer_url": "http://127.0.0.1:9"})  # port 9: nothing listens, pokes fail fast

    def tearDown(self):
        self.tmp.cleanup()

    def test_help_lists_core_and_capability_commands(self):
        write_cap(self.caps, "hello", HELLO, commands=HELLO_CMD)
        code, out, _ = run_cli(self.data, "help")
        self.assertEqual(code, 0)
        self.assertIn("orbit greet", out)
        self.assertIn("hello [name]", out)
        self.assertIn("[hello]", out)

    def test_command_prints_and_renders(self):
        write_cap(self.caps, "hello", HELLO, commands=HELLO_CMD)
        code, out, _ = run_cli(self.data, "hello", "Gabby")
        self.assertEqual(code, 0)
        self.assertIn("hello, Gabby!", out)
        self.assertIn("hi Gabby", out)
        self.assertIn("Charon", out)

    def test_unknown_command(self):
        code, _, err = run_cli(self.data, "nope")
        self.assertEqual(code, 1)
        self.assertIn("orbit help", err)

    def test_failing_command_reports_error_and_stderr(self):
        write_cap(self.caps, "bad", py('print("bad input", file=sys.stderr)\nsys.exit(2)'),
                  commands=[{"name": "bad", "usage": "bad", "help": "fails"}])
        code, _, err = run_cli(self.data, "bad")
        self.assertEqual(code, 1)
        self.assertIn("exited with code 2", err)
        self.assertIn("bad input", err)

    def test_command_emits_are_stored_and_a_dead_peer_is_harmless(self):
        write_cap(self.caps, "ping", py('print(json.dumps({"emit": [{"type": "ping.sent", "data": {}}]}))'),
                  commands=[{"name": "ping", "usage": "ping", "help": "ping"}],
                  event_types={"ping.sent": {"keep": "log"}})
        start = time.monotonic()
        code, _, _ = run_cli(self.data, "ping")
        self.assertEqual(code, 0)
        self.assertLess(time.monotonic() - start, 3)
        store = Store(self.data / "orbit.db", "charon")
        try:
            self.assertEqual(len(store.recent(["ping.sent"])), 1)
        finally:
            store.close()

    def test_greet_runs_login_capabilities_in_parallel(self):
        for name in ("one", "two"):
            write_cap(self.caps, name, py(f'''
                time.sleep(0.5)
                print(json.dumps({{"say": [{{"who": "pluto", "mood": "happy", "text": "from {name}"}}]}}))
            '''), triggers=["login"])
        start = time.monotonic()
        code, out, _ = run_cli(self.data, "greet")
        self.assertLess(time.monotonic() - start, 0.95)
        self.assertEqual(code, 0)
        self.assertIn("from one", out)
        self.assertIn("from two", out)

    def test_greet_puts_a_divider_between_capabilities_only(self):
        from orbit import characters
        for name, texts in (("one", ["greeting"]), ("two", ["note a", "note b"])):
            says = [{"who": "pluto", "mood": "happy", "text": t} for t in texts]
            write_cap(self.caps, name, py(f"print(json.dumps({{'say': {says!r}}}))"), triggers=["login"])
        out = run_cli(self.data, "greet")[1]
        line = characters.divider()
        self.assertEqual(out.count(line), 1)
        self.assertLess(out.index("greeting"), out.index(line))
        self.assertLess(out.index(line), out.index("note a"))
        self.assertNotIn(line, out[out.index("note a"):])  # no divider inside one capability's bubbles

    def test_greet_skips_a_broken_capability_quietly(self):
        write_cap(self.caps, "broken", py("sys.exit(1)"), triggers=["login"])
        write_cap(self.caps, "fine", py('print(json.dumps({"say": [{"who": "charon", "mood": "happy", "text": "ok"}]}))'),
                  triggers=["login"])
        code, out, err = run_cli(self.data, "greet")
        self.assertEqual(code, 0)
        self.assertIn("ok", out)
        self.assertEqual(err, "")

    def test_print_output_has_control_characters_stripped(self):
        write_cap(self.caps, "evil", py('print(json.dumps({"print": "\\u001b[2Jboom\\nline two"}))'),
                  commands=[{"name": "evil", "usage": "evil", "help": "prints escapes"}])
        code, out, _ = run_cli(self.data, "evil")
        self.assertEqual(code, 0)
        self.assertNotIn("\x1b", out)
        self.assertIn("[2Jboom\nline two", out)

    def test_greet_without_a_terminal_does_nothing(self):
        write_cap(self.caps, "seen", py(
            'print(json.dumps({"say": [{"who": "pluto", "mood": "love", "text": "a note"}], '
            '"emit": [{"type": "seen.read", "data": {}}]}))'),
            triggers=["login"], event_types={"seen.read": {"keep": "log"}})
        code, out, _ = run_cli(self.data, "greet", env={"ORBIT_FORCE_GREET": ""})
        self.assertEqual((code, out), (0, ""))
        store = Store(self.data / "orbit.db", "charon")
        try:
            self.assertEqual(store.recent(["seen.read"]), [])
        finally:
            store.close()

    def test_greet_shows_says_before_applying_and_survives_apply_errors(self):
        write_cap(self.caps, "seen", py(
            'print(json.dumps({"say": [{"who": "pluto", "mood": "love", "text": "a note"}], '
            '"emit": [{"type": "seen.read", "data": {}}]}))'),
            triggers=["login"], event_types={"seen.read": {"keep": "log"}})
        shown_first = []

        def failing_apply(rt, m, out, kind):
            shown_first.append("a note" in sys.stdout.getvalue())
            raise RuntimeError("disk full")

        with mock.patch("orbit.loader.apply", side_effect=failing_apply):
            code, out, _ = run_cli(self.data, "greet")
        self.assertEqual(code, 0)
        self.assertIn("a note", out)
        self.assertEqual(shown_first, [True])
        self.assertIn("RuntimeError: disk full", (self.data / "logs" / "seen.log").read_text(encoding="utf-8"))

    def test_missing_config_says_run_init(self):
        code, _, err = run_cli(self.root / "empty", "help")
        self.assertEqual(code, 1)
        self.assertIn("orbit init", err)

    def test_init_writes_config_and_refuses_to_overwrite(self):
        fresh = self.root / "fresh"
        self.assertEqual(run_cli(fresh, "init", "--me", "pluto", "--peer", "charon")[0], 0)
        self.assertEqual(config.load(fresh).me, "pluto")
        code, _, err = run_cli(fresh, "init", "--me", "pluto", "--peer", "charon")
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)

    def test_init_dev_points_at_the_dev_peer(self):
        fresh = self.root / "fresh"
        run_cli(fresh, "init", "--me", "charon", "--peer", "pluto", "--dev")
        cfg = config.load(fresh)
        self.assertEqual(cfg.bind, "127.0.0.1")
        self.assertEqual(cfg.peer_url, "http://127.0.0.1:1979")
        self.assertEqual(cfg.dev_allow_ips, ["127.0.0.1"])

    def init_with_home(self, env: dict) -> tuple[int, str]:
        """Run `orbit init --dev` with HOME pointed at a temp folder (never the real one)."""
        home = self.root / "home"
        home.mkdir(exist_ok=True)
        err = io.StringIO()
        clean = {k: v for k, v in os.environ.items() if k != "ORBIT_DIR"}
        with mock.patch.dict(os.environ, {**clean, "HOME": str(home), **env}, clear=True), \
                redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = cli.main(["init", "--me", "charon", "--peer", "pluto", "--dev"])
        return code, err.getvalue()

    def test_init_dev_in_the_real_folder_warns_but_writes(self):
        code, err = self.init_with_home({})
        self.assertEqual(code, 0)
        self.assertIn("ORBIT_DIR=~/.orbit-dev", err)
        self.assertEqual(err.count("\n"), 1)
        self.assertTrue((self.root / "home" / ".orbit" / "config.json").exists())

    def test_init_dev_with_a_separate_orbit_dir_is_quiet(self):
        code, err = self.init_with_home({"ORBIT_DIR": str(self.root / "home" / ".orbit-dev")})
        self.assertEqual((code, err), (0, ""))
