import json
import tempfile
import time
import unittest
from pathlib import Path

from orbit import sync
from tests.helpers import FakePeer, make_cfg, make_runtime, py, write_cap

TS = "2026-10-03T14:00:00Z"


def ev(seq, type="ping.sent", data=None, keep="log", origin="pluto"):
    return {"origin": origin, "seq": seq, "type": type, "ts": TS, "v": 1, "data": data or {}, "keep": keep}


def page(events, has_more=False, instance=None):
    body = {"events": events, "has_more": has_more, "core_version": "0.1.0", "capabilities": []}
    if instance is not None:
        body["instance"] = instance
    return 200, json.dumps(body).encode()


COUNT_PINGS = py('''
n = sum(1 for e in inp["events"] if e["origin"] == inp["peer"]["name"] and e["type"] == "ping.sent")
print(json.dumps({"prompt": f"got {n}"}))
''')


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.caps = root / "caps"
        self.caps.mkdir()
        self.data = root / "data"
        write_cap(self.caps, "ping", COUNT_PINGS, triggers=["received"], receives=["ping.sent"],
                  event_types={"ping.sent": {"keep": "log"}})
        self.responses: list = []
        self.peer = FakePeer(self.respond)
        self.rt = make_runtime(self.data, self.caps, peer_url=self.peer.url)

    def tearDown(self):
        self.peer.close()
        self.rt.store.close()
        self.tmp.cleanup()

    def respond(self, method, path):
        if method == "POST":
            return 204, b""
        return self.responses.pop(0) if self.responses else page([])

    def log_text(self) -> str:
        return (self.data / "logs" / "orbitd.log").read_text(encoding="utf-8")

    def test_pull_stores_events_advances_cursor_and_marks_online(self):
        self.responses = [page([ev(1), ev(2)])]
        self.assertTrue(sync.pull_once(self.rt))
        self.assertEqual(len(self.rt.store.recent(["ping.sent"])), 2)
        self.assertEqual(self.rt.store.peer_cursor(), 2)
        self.assertTrue(self.rt.store.peer_status()["online"])

    def test_pull_follows_has_more(self):
        self.responses = [page([ev(1), ev(2)], has_more=True), page([ev(3)])]
        sync.pull_once(self.rt)
        self.assertEqual(self.rt.store.peer_cursor(), 3)
        paths = [p for m, p in self.peer.requests if m == "GET"]
        self.assertIn("after=0", paths[0])
        self.assertIn("after=2", paths[1])

    def test_latest_events_go_to_the_latest_table(self):
        self.responses = [page([ev(4, type="presence.status", data={"state": "idle"}, keep="latest")])]
        sync.pull_once(self.rt)
        self.assertEqual(self.rt.store.latest_all()["pluto"]["presence.status"].data, {"state": "idle"})

    def test_bad_events_are_skipped_and_the_cursor_moves_past(self):
        self.responses = [page([ev(1), ev(2, origin="charon"), ev(3, type="NOPE"), "junk"])]
        self.assertTrue(sync.pull_once(self.rt))
        self.assertEqual([e.seq for e in self.rt.store.recent(["ping.sent"])], [1])
        self.assertEqual(self.rt.store.peer_cursor(), 3)
        self.assertIn("skipped a bad event", self.log_text())

    def test_received_trigger_gets_only_matching_types(self):
        self.responses = [page([ev(1), ev(2, type="other.thing")])]
        sync.pull_once(self.rt)
        self.assertEqual(self.rt.cfg.prompt_path.read_text(encoding="utf-8"), "got 1")

    def test_new_peer_installation_is_forgotten_and_resynced(self):
        self.responses = [page([ev(1, data={"n": "old1"}), ev(2, data={"n": "old2"}),
                                ev(3, type="presence.status", data={"state": "idle"}, keep="latest")],
                               instance="A")]
        sync.pull_once(self.rt)
        self.assertEqual(self.rt.store.peer_cursor(), 3)
        # The new installation has nothing after seq 3; once forgotten, we re-ask from 0.
        self.responses = [page([], instance="B"), page([ev(1, data={"n": "new1"})], instance="B")]
        self.assertTrue(sync.pull_once(self.rt))
        self.assertEqual([e.data for e in self.rt.store.recent(["ping.sent"])], [{"n": "new1"}])
        self.assertNotIn("pluto", self.rt.store.latest_all())
        self.assertEqual(self.rt.store.peer_cursor(), 1)
        self.assertEqual(self.rt.store.get_meta("peer_instance"), "B")
        self.assertIn("new installation", self.log_text())
        gets = [p for m, p in self.peer.requests if m == "GET"]
        self.assertIn("after=0", gets[-1])  # re-asked from the start

    def test_flapping_instance_cannot_loop_forever(self):
        self.responses = [page([ev(1)], instance="A"), page([], instance="B"), page([], instance="C")]
        sync.pull_once(self.rt)
        self.assertFalse(sync.pull_once(self.rt))
        self.assertIn("instance id twice", self.log_text())

    def test_same_instance_keeps_events(self):
        self.responses = [page([ev(1)], instance="A"), page([ev(2)], instance="A")]
        sync.pull_once(self.rt)
        sync.pull_once(self.rt)
        self.assertEqual(len(self.rt.store.recent(["ping.sent"])), 2)
        self.assertEqual(self.rt.store.get_meta("peer_instance"), "A")

    def test_non_json_peer_is_offline_not_a_crash(self):  # Review Focus #4
        self.responses = [(200, b"<html>hello</html>")]
        self.assertFalse(sync.pull_once(self.rt))
        self.assertFalse(self.rt.store.peer_status()["online"])
        self.assertIn("isn't JSON", self.log_text())

    def test_403_is_offline_with_a_hint(self):  # Review Focus #4
        self.responses = [(403, b'{"error": "not the configured peer"}')]
        self.assertFalse(sync.pull_once(self.rt))
        self.assertIn("peer_host", self.log_text())

    def test_same_error_is_logged_once(self):
        self.responses = [(403, b"{}"), (403, b"{}")]
        sync.pull_once(self.rt)
        sync.pull_once(self.rt)
        self.assertEqual(self.log_text().count("HTTP 403"), 1)

    def test_unreachable_peer_fails_fast(self):
        rt = make_runtime(self.data, self.caps, peer_url="http://127.0.0.1:9")
        try:
            start = time.monotonic()
            self.assertFalse(sync.pull_once(rt))
            self.assertLess(time.monotonic() - start, 3)
        finally:
            rt.store.close()

    def test_poke_peer(self):
        self.assertTrue(sync.poke_peer(self.rt.cfg))
        self.assertFalse(sync.poke_peer(make_cfg(self.data, peer_url="http://127.0.0.1:9")))

    def test_validate_incoming_rejections(self):
        for raw, why in [(ev(1, origin="charon"), "origin"), ({**ev(1), "seq": True}, "seq"),
                         (ev(1, data={"x": "y" * 17000}), "16384"), ({**ev(1), "keep": "forever"}, "keep"),
                         ({**ev(1), "data": []}, "data")]:
            with self.subTest(why=why), self.assertRaises(ValueError) as ctx:
                sync.validate_incoming(raw, "pluto")
            self.assertIn(why, str(ctx.exception))

    def test_backoff(self):
        b = sync.Backoff()
        self.assertEqual([b.next() for _ in range(8)], [5, 10, 20, 40, 80, 160, 300, 300])
        b.reset()
        self.assertEqual(b.next(), 5)
