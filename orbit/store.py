"""SQLite event store: this machine's events plus copies of the peer's.

Each machine is the only author of its own events (origin = me). The peer's events
arrive via sync and are inserted as-is. Events are never edited. "latest" events
(e.g. presence) keep only the newest per (origin, type), but they take a seq like
any other event, so the sync cursor covers both tables.

One connection per thread (sqlite3 connections aren't thread-safe); WAL mode lets
the CLI and the daemon use the file at the same time.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from orbit.contract import KEEPS, MAX_DATA_BYTES

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,  -- arrival order on this machine
    origin TEXT NOT NULL, seq INTEGER NOT NULL, type TEXT NOT NULL,
    ts TEXT NOT NULL, v INTEGER NOT NULL, data TEXT NOT NULL,
    UNIQUE (origin, seq)
);
CREATE INDEX IF NOT EXISTS events_type ON events (type);
CREATE TABLE IF NOT EXISTS latest (
    origin TEXT NOT NULL, type TEXT NOT NULL, seq INTEGER NOT NULL,
    ts TEXT NOT NULL, v INTEGER NOT NULL, data TEXT NOT NULL,
    PRIMARY KEY (origin, type)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
COLS = "origin, seq, type, ts, v, data"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Event:
    origin: str
    seq: int
    type: str
    ts: str
    v: int
    data: dict

    def to_dict(self) -> dict:
        return {"origin": self.origin, "seq": self.seq, "type": self.type,
                "ts": self.ts, "v": self.v, "data": self.data}


def _event(row: tuple) -> Event:
    return Event(row[0], row[1], row[2], row[3], row[4], json.loads(row[5]))


def _payload(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    size = len(text.encode())
    if size > MAX_DATA_BYTES:
        raise ValueError(f"event data is {size} bytes; the limit is {MAX_DATA_BYTES}")
    return text


class Store:
    def __init__(self, path: Path, me: str):
        self.path = path
        self.me = me
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._conn()
        conn.executescript(SCHEMA)
        # A random id per database, so the peer can tell a reinstall (or a dev-mode
        # database) from the machine it synced with before; see sync.pull_once.
        conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('instance', ?)", (uuid.uuid4().hex,))

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=2.0, isolation_level=None, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=2000")
            self._local.conn = conn
            with self._lock:
                self._all.append(conn)
        return conn

    def close(self) -> None:
        """Close every connection this Store opened, from any thread. Safe to call twice; the Store reopens on next use."""
        with self._lock:
            conns, self._all = self._all, []
        for conn in conns:
            conn.close()
        self._local = threading.local()

    def release(self) -> None:
        """Close the calling thread's connection, if any. Per-request threads call this so connections don't pile up."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            return
        self._local.conn = None
        with self._lock:
            if conn in self._all:
                self._all.remove(conn)
        conn.close()

    # ---- writing ----

    def append(self, type: str, data: dict, keep: str = "log", v: int = 1) -> Event:
        """Record a new event authored by this machine."""
        if keep not in KEEPS:
            raise ValueError(f"keep must be one of {KEEPS}, got {keep!r}")
        payload = _payload(data)
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")  # serializes seq allocation across processes
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'next_seq'").fetchone()
            seq = int(row[0]) if row else 1
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('next_seq', ?)", (str(seq + 1),))
            event = Event(self.me, seq, type, now_iso(), v, data)
            self._write(conn, event, keep, payload)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        return event

    def insert(self, event: Event, keep: str) -> bool:
        """Store a copy of a peer event. Safe to repeat; returns True only if it was new."""
        if keep not in KEEPS:
            raise ValueError(f"keep must be one of {KEEPS}, got {keep!r}")
        return self._write(self._conn(), event, keep, _payload(event.data))

    def forget_origin(self, origin: str) -> None:
        """Drop every stored event from `origin`.

        The one exception to "events are never deleted": it's used only when the peer
        turns out to be a different installation (new instance id), so its old events
        and seqs belong to a database that no longer exists and would block the new one's.
        """
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM events WHERE origin = ?", (origin,))
            conn.execute("DELETE FROM latest WHERE origin = ?", (origin,))
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def _write(self, conn: sqlite3.Connection, e: Event, keep: str, payload: str) -> bool:
        values = (e.origin, e.seq, e.type, e.ts, e.v, payload)
        if keep == "log":
            cur = conn.execute(f"INSERT OR IGNORE INTO events ({COLS}) VALUES (?, ?, ?, ?, ?, ?)", values)
        else:
            cur = conn.execute(
                "INSERT INTO latest (origin, seq, type, ts, v, data) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (origin, type) DO UPDATE SET seq = excluded.seq, ts = excluded.ts, "
                "v = excluded.v, data = excluded.data WHERE excluded.seq > latest.seq", values)
        return cur.rowcount == 1

    # ---- reading ----

    def recent(self, types: Iterable[str], limit: int = 200) -> list[Event]:
        """Newest `limit` log events of these types, returned oldest first by arrival."""
        types = list(types)
        if not types:
            return []
        marks = ", ".join("?" for _ in types)
        rows = self._conn().execute(
            f"SELECT {COLS} FROM (SELECT id, {COLS} FROM events WHERE type IN ({marks}) "
            f"ORDER BY id DESC LIMIT ?) ORDER BY id ASC", (*types, limit)).fetchall()
        return [_event(r) for r in rows]

    def latest_all(self) -> dict[str, dict[str, Event]]:
        out: dict[str, dict[str, Event]] = {}
        for row in self._conn().execute(f"SELECT {COLS} FROM latest"):
            e = _event(row)
            out.setdefault(e.origin, {})[e.type] = e
        return out

    def own_after(self, after: int, limit: int) -> list[tuple[Event, str]]:
        """This machine's events with seq > after, from both tables, in seq order (what the peer pulls)."""
        conn = self._conn()
        q = f"SELECT {COLS} FROM {{}} WHERE origin = ? AND seq > ? ORDER BY seq LIMIT ?"
        rows = [(r, "log") for r in conn.execute(q.format("events"), (self.me, after, limit))]
        rows += [(r, "latest") for r in conn.execute(q.format("latest"), (self.me, after, limit))]
        rows.sort(key=lambda pair: pair[0][1])
        return [(_event(r), keep) for r, keep in rows[:limit]]

    # ---- meta ----

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self._conn().execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self._conn().execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    def instance(self) -> str:
        """This database's random id (made on first open)."""
        return self.get_meta("instance") or ""

    def delete_meta(self, key: str) -> None:
        self._conn().execute("DELETE FROM meta WHERE key = ?", (key,))

    def peer_status(self) -> dict:
        return {"online": self.get_meta("peer_online") == "1", "last_seen": self.get_meta("peer_last_seen")}

    def set_peer_status(self, online: bool, last_seen: str | None) -> None:
        self.set_meta("peer_online", "1" if online else "0")
        if last_seen is not None:
            self.set_meta("peer_last_seen", last_seen)

    def peer_cursor(self) -> int:
        return int(self.get_meta("peer_cursor") or 0)

    def set_peer_cursor(self, seq: int) -> None:
        self.set_meta("peer_cursor", str(seq))
