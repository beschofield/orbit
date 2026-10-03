import os
import tempfile
import time
import unittest
from pathlib import Path

from orbit import loader
from tests.helpers import make_runtime, py, write_cap

EMIT_AND_PROMPT = py('print(json.dumps({"emit": [{"type": "ping.sent", "data": {"n": 1}}], "prompt": "p!"}))')
NOTHING = py('print("{}")')


class LoaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.caps = root / "caps"
        self.caps.mkdir()
        self.data = root / "data"
        self.runtimes = []

    def tearDown(self):
        for rt in self.runtimes:
            rt.store.close()
        self.tmp.cleanup()

    def runtime(self, **extra):
        return self.track(make_runtime(self.data, self.caps, **extra))

    def track(self, rt):
        self.runtimes.append(rt)
        return rt

    def log_text(self, name: str) -> str:
        return (self.data / "logs" / f"{name}.log").read_text(encoding="utf-8")

    def test_discover_reports_bad_manifests_and_keeps_good_ones(self):
        write_cap(self.caps, "good", NOTHING)
        write_cap(self.caps, "bad", NOTHING, event_types={"oops": {"keep": "log"}})
        rt = self.runtime()
        self.assertEqual(list(rt.manifests), ["good"])
        self.assertTrue(any('event_types."oops"' in p for p in rt.problems), rt.problems)

    def test_unreadable_manifest_is_a_problem_not_a_crash(self):
        write_cap(self.caps, "good", NOTHING)
        d = write_cap(self.caps, "garbled", NOTHING)
        (d / "manifest.json").write_bytes(b'{"name": "\xff\xfe"}')
        rt = self.runtime()
        self.assertEqual(list(rt.manifests), ["good"])
        self.assertTrue(any(p.startswith(f"{d}/manifest.json: could not read (UnicodeDecodeError")
                            and p.endswith("fix the file") for p in rt.problems), rt.problems)

    def test_login_timeouts_are_logged_but_never_disable(self):
        write_cap(self.caps, "slow", py('time.sleep(2)\nprint("{}")'), triggers=["login"])
        rt = self.runtime()
        m = rt.manifests["slow"]
        for _ in range(loader.MAX_FAILURES):
            self.assertIn("timed out", loader.run(rt, m, {"kind": "login"}).error)
        self.assertFalse(loader.is_disabled(rt, m))
        self.assertIsNone(rt.store.get_meta("fail:slow"))
        self.assertIn("timed out", self.log_text("slow"))

    def test_missing_capabilities_dir_is_a_problem(self):
        rt = self.track(make_runtime(self.data, self.caps / "nope"))
        self.assertEqual(rt.manifests, {})
        self.assertIn("capabilities_dir", rt.problems[0])

    def test_duplicate_commands_go_to_neither(self):
        cmd = [{"name": "hi", "usage": "hi", "help": "say hi"}]
        write_cap(self.caps, "one", NOTHING, commands=cmd)
        write_cap(self.caps, "two", NOTHING, commands=cmd)
        rt = self.runtime()
        self.assertNotIn("hi", rt.commands())
        self.assertTrue(any("'hi' is declared by one, two" in p for p in rt.problems), rt.problems)

    def test_build_input_has_own_types_only_and_both_latest_keys(self):
        write_cap(self.caps, "ping", NOTHING, event_types={"ping.sent": {"keep": "log"}})
        rt = self.runtime()
        rt.store.append("ping.sent", {"n": 1})
        rt.store.append("other.thing", {"n": 2})
        inp = loader.build_input(rt, rt.manifests["ping"], {"kind": "tick"})
        self.assertEqual(inp["contract"], 1)
        self.assertEqual([e["type"] for e in inp["events"]], ["ping.sent"])
        self.assertEqual(set(inp["latest"]), {"charon", "pluto"})
        self.assertEqual(inp["peer"], {"name": "pluto", "online": False, "last_seen": None})
        self.assertEqual(inp["me"], {"name": "charon"})

    def test_execute_success(self):
        write_cap(self.caps, "ping", EMIT_AND_PROMPT, event_types={"ping.sent": {"keep": "log"}})
        rt = self.runtime()
        m = rt.manifests["ping"]
        res = loader.execute(m, loader.build_input(rt, m, {"kind": "tick"}), 5)
        self.assertIsNone(res.error)
        self.assertEqual(res.output.prompt, "p!")

    def test_execute_timeout(self):
        write_cap(self.caps, "slow", py('time.sleep(3)\nprint("{}")'))
        m = self.runtime().manifests["slow"]
        start = time.monotonic()
        res = loader.execute(m, {}, 0.3)
        self.assertLess(time.monotonic() - start, 2)
        self.assertIn("timed out after 0.3s", res.error)

    def test_execute_nonzero_exit_keeps_stderr(self):
        write_cap(self.caps, "boom", py('print("kaboom", file=sys.stderr)\nsys.exit(3)'))
        res = loader.execute(self.runtime().manifests["boom"], {}, 5)
        self.assertIn("exited with code 3", res.error)
        self.assertIn("kaboom", res.stderr)

    def test_invalid_utf8_output_is_a_contract_error_not_a_crash(self):
        d = write_cap(self.caps, "bytes", "#!/bin/sh\nprintf '\\377\\376 not utf8'; printf '\\377' >&2\n")
        res = loader.execute(self.runtime().manifests[d.name], {}, 5)
        self.assertIsNone(res.output)
        self.assertTrue(res.error)

    def test_unicode_round_trips(self):
        write_cap(self.caps, "echo", py('print(json.dumps({"print": inp["trigger"]["args"][0]}, ensure_ascii=False))'))
        res = loader.execute(self.runtime().manifests["echo"], {"trigger": {"args": ["💤 ♥ café"]}}, 5)
        self.assertIsNone(res.error)
        self.assertEqual(res.output.print_text, "💤 ♥ café")

    def test_debug_output_on_stdout_fails_with_the_fix(self):  # Review Focus #5
        write_cap(self.caps, "chatty", py('print("debug: hello")\nprint("{}")'))
        write_cap(self.caps, "calm", NOTHING)
        rt = self.runtime()
        res = loader.run(rt, rt.manifests["chatty"], {"kind": "tick"})
        self.assertIsNone(res.output)
        self.assertIn("send debug output to stderr", self.log_text("chatty"))
        self.assertIsNotNone(loader.run(rt, rt.manifests["calm"], {"kind": "tick"}).output)

    def test_disabled_after_five_failures_and_reenabled_by_an_edit(self):
        d = write_cap(self.caps, "boom", py("sys.exit(1)"))
        rt = self.runtime()
        m = rt.manifests["boom"]
        for _ in range(5):
            loader.run(rt, m, {"kind": "tick"})
        self.assertTrue(loader.is_disabled(rt, m))
        self.assertIn("disabled", loader.run(rt, m, {"kind": "tick"}).error)
        self.assertIn("DISABLED", self.log_text("boom"))
        future = time.time() + 10
        os.utime(d / "main.py", (future, future))
        self.assertFalse(loader.is_disabled(rt, m))

    def test_success_resets_the_failure_count(self):
        flag = self.data.parent / "fail-now"
        write_cap(self.caps, "flaky", py(f"sys.exit(1 if os.path.exists({str(flag)!r}) else 0)"))
        rt = self.runtime()
        m = rt.manifests["flaky"]
        flag.touch()
        for _ in range(4):
            loader.run(rt, m, {"kind": "tick"})
        flag.unlink()
        loader.run(rt, m, {"kind": "tick"})
        flag.touch()
        for _ in range(4):
            loader.run(rt, m, {"kind": "tick"})
        self.assertFalse(loader.is_disabled(rt, m))

    def test_reset_reenables(self):
        write_cap(self.caps, "boom", py("sys.exit(1)"))
        rt = self.runtime()
        m = rt.manifests["boom"]
        for _ in range(5):
            loader.run(rt, m, {"kind": "tick"})
        loader.reset(rt, "boom")
        self.assertFalse(loader.is_disabled(rt, m))

    def test_invoke_stores_emits_with_manifest_keep_and_writes_prompt(self):
        write_cap(self.caps, "ping", EMIT_AND_PROMPT, event_types={"ping.sent": {"keep": "latest"}})
        rt = self.runtime()
        loader.invoke(rt, rt.manifests["ping"], {"kind": "tick"})
        self.assertEqual(rt.store.recent(["ping.sent"]), [])
        self.assertEqual(rt.store.latest_all()["charon"]["ping.sent"].data, {"n": 1})
        self.assertEqual(rt.cfg.prompt_path.read_text(encoding="utf-8"), "p!")

    def test_say_from_a_tick_is_logged_not_shown(self):
        write_cap(self.caps, "talky", py('print(json.dumps({"say": [{"who": "pluto", "mood": "happy", "text": "hi"}]}))'),
                  triggers=["tick"], tick_seconds=60)
        rt = self.runtime()
        loader.invoke(rt, rt.manifests["talky"], {"kind": "tick"})
        self.assertIn("say is ignored for tick", self.log_text("talky"))
