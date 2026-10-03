import json
import tempfile
import unittest
from pathlib import Path

from orbit import config
from orbit.store import Store
from tests.helpers import py, run_cli, write_cap

HELLO = py('''
name = " ".join(inp["trigger"]["args"]) or "friend"
print(json.dumps({"print": f"hello, {name}!", "emit": [{"type": "hello.said", "data": {"to": name}}]}))
''')


class DevToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.caps = root / "caps"
        self.caps.mkdir()
        self.data = root / "data"
        config.write(self.data, {"me": "charon", "peer": "pluto", "capabilities_dir": str(self.caps),
                                 "peer_url": "http://127.0.0.1:9"})
        self.cap = write_cap(self.caps, "hello", HELLO,
                             commands=[{"name": "hello", "usage": "hello [name]", "help": "hi"}],
                             event_types={"hello.said": {"keep": "log"}})

    def tearDown(self):
        self.tmp.cleanup()

    def case(self, name: str, args: list[str], expect: dict) -> None:
        (self.cap / "tests").mkdir(exist_ok=True)
        (self.cap / "tests" / f"{name}.json").write_text(json.dumps({
            "input": {"trigger": {"kind": "command", "name": "hello", "args": args}}, "expect": expect}))

    def test_dev_run_shows_input_and_output_and_writes_nothing(self):
        code, out, _ = run_cli(self.data, "dev", "run", "hello", "command", "hello", "Gabby")
        self.assertEqual(code, 0)
        self.assertIn("── input ──", out)
        self.assertIn('"hello.said"', out)
        self.assertIn("hello, Gabby!", out)
        store = Store(self.data / "orbit.db", "charon")
        try:
            self.assertEqual(store.recent(["hello.said"]), [])
        finally:
            store.close()

    def test_dev_run_unknown_capability(self):
        code, _, err = run_cli(self.data, "dev", "run", "nope", "login")
        self.assertEqual(code, 1)
        self.assertIn("loaded: hello", err)

    def test_dev_without_subcommand_prints_usage(self):
        code, _, err = run_cli(self.data, "dev")
        self.assertEqual(code, 2)
        self.assertIn("orbit dev test", err)

    def test_dev_test_passes_and_fails_with_a_diff(self):
        self.case("good", ["Gabby"], {"print": "hello, Gabby!"})
        self.assertEqual(run_cli(self.data, "dev", "test", "hello")[0], 0)
        self.case("bad", ["Gabby"], {"print": "nope"})
        code, out, _ = run_cli(self.data, "dev", "test", "hello")
        self.assertEqual(code, 1)
        self.assertIn("1 failing", out)
        self.assertIn('expected "nope"', out)

    def test_dev_test_requires_cases(self):
        code, out, _ = run_cli(self.data, "dev", "test")
        self.assertEqual(code, 1)
        self.assertIn("no test cases", out)
