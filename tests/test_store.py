import tempfile
import threading
import unittest
from pathlib import Path

from orbit.store import Event, Store

TS = "2026-10-03T14:00:00Z"


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "orbit.db"
        self.store = Store(self.path, "charon")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_append_assigns_increasing_seq_and_origin(self):
        a = self.store.append("notes.sent", {"text": "a"})
        b = self.store.append("notes.sent", {"text": "b"})
        self.assertEqual((a.seq, b.seq), (1, 2))
        self.assertEqual(a.origin, "charon")
        self.assertTrue(a.ts.endswith("Z"))

    def test_insert_is_idempotent(self):
        ev = Event("pluto", 1, "notes.sent", TS, 1, {"text": "hi"})
        self.assertTrue(self.store.insert(ev, "log"))
        self.assertFalse(self.store.insert(ev, "log"))
        self.assertEqual(len(self.store.recent(["notes.sent"])), 1)

    def test_latest_keeps_highest_seq_and_stays_out_of_log(self):
        self.assertTrue(self.store.insert(Event("pluto", 5, "presence.status", TS, 1, {"state": "idle"}), "latest"))
        self.assertFalse(self.store.insert(Event("pluto", 3, "presence.status", TS, 1, {"state": "active"}), "latest"))
        self.assertEqual(self.store.latest_all()["pluto"]["presence.status"].data, {"state": "idle"})
        self.assertEqual(self.store.recent(["presence.status"]), [])

    def test_own_after_covers_both_tables_in_seq_order(self):
        self.store.append("notes.sent", {"text": "a"})                             # 1
        self.store.append("presence.status", {"state": "active"}, keep="latest")   # 2
        self.store.append("notes.sent", {"text": "b"})                             # 3
        self.store.insert(Event("pluto", 9, "notes.sent", TS, 1, {"text": "x"}), "log")
        rows = self.store.own_after(1, 10)
        self.assertEqual([(e.seq, k) for e, k in rows], [(2, "latest"), (3, "log")])
        self.assertEqual([e.seq for e, _ in self.store.own_after(0, 2)], [1, 2])

    def test_recent_orders_by_arrival_not_timestamp(self):  # Review Focus #3
        self.store.insert(Event("pluto", 1, "notes.sent", "2030-01-01T00:00:00Z", 1, {"text": "future"}), "log")
        self.store.append("notes.sent", {"text": "now"})
        self.store.insert(Event("pluto", 2, "notes.sent", "2001-01-01T00:00:00Z", 1, {"text": "past"}), "log")
        self.assertEqual([e.data["text"] for e in self.store.recent(["notes.sent"])], ["future", "now", "past"])

    def test_recent_limit_keeps_newest_and_filters_types(self):
        for i in range(5):
            self.store.append("notes.sent", {"i": i})
        self.store.append("other.thing", {})
        self.assertEqual([e.data["i"] for e in self.store.recent(["notes.sent"], limit=2)], [3, 4])
        self.assertEqual(self.store.recent([]), [])

    def test_rejects_oversized_data(self):
        with self.assertRaises(ValueError):
            self.store.append("notes.sent", {"text": "x" * 17000})

    def test_meta_peer_status_and_cursor(self):
        self.assertEqual(self.store.peer_status(), {"online": False, "last_seen": None})
        self.store.set_peer_status(True, TS)
        self.store.set_peer_status(False, None)
        self.assertEqual(self.store.peer_status(), {"online": False, "last_seen": TS})
        self.assertEqual(self.store.peer_cursor(), 0)
        self.store.set_peer_cursor(7)
        self.assertEqual(self.store.peer_cursor(), 7)
        self.store.set_meta("k", "v")
        self.store.delete_meta("k")
        self.assertEqual(self.store.get_meta("k", "default"), "default")

    def test_concurrent_appends_from_two_stores_get_unique_seqs(self):
        other = Store(self.path, "charon")  # e.g. the CLI and the daemon at once

        def work(store):
            for _ in range(25):
                store.append("notes.sent", {})

        threads = [threading.Thread(target=work, args=(s,)) for s in (self.store, other, self.store, other)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        other.close()
        seqs = sorted(e.seq for e, _ in self.store.own_after(0, 500))
        self.assertEqual(seqs, list(range(1, 101)))

    def test_close_is_idempotent_and_store_reopens(self):
        self.store.append("notes.sent", {"text": "a"})
        self.store.close()
        self.store.close()  # should be safe to call twice
        b = self.store.append("notes.sent", {"text": "b"})
        self.assertEqual(b.seq, 2)  # reopened and continues seq

    def test_close_from_main_thread_closes_connections_opened_by_other_threads(self):
        def worker():
            self.store.append("notes.sent", {})

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(self.store._all), 4)  # 1 main thread + 3 worker threads
        self.store.close()
        self.assertEqual(self.store._all, [])
        # verify store still works after close
        b = self.store.append("notes.sent", {"text": "test"})
        self.assertEqual(b.seq, 4)
