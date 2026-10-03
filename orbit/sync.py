"""Peer sync: each machine pulls the other's events; pokes make it happen right away.

Each machine is the only source of truth for its own events, so there are no
conflicts to merge. A pull asks for "your events after seq N" and stores what
arrives. Inserts are idempotent, so retries and lost pokes are harmless; the 30 s
pull catches up. Bad events are logged and skipped, but the cursor still moves past
them so one bad event can't block sync forever.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from orbit import loader
from orbit.config import Config
from orbit.contract import KEEPS, MAX_DATA_BYTES, TYPE_RE
from orbit.log import log
from orbit.store import Event, now_iso

PULL_INTERVAL = 30.0
PAGE = 500


class PeerError(Exception):
    """The peer couldn't be reached or answered with something unusable."""


class Backoff:
    def __init__(self, first: float = 5.0, cap: float = 300.0):
        self.first, self.cap, self.current = first, cap, 0.0

    def next(self) -> float:
        self.current = self.first if self.current == 0 else min(self.current * 2, self.cap)
        return self.current

    def reset(self) -> None:
        self.current = 0.0


def get_json(url: str, timeout: float = 2.0) -> dict | None:
    """GET a JSON object, or None on any failure (for doctor's yes/no checks)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read())
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def fetch_events(peer_url: str, after: int, limit: int = PAGE, timeout: float = 5.0) -> dict:
    try:
        with urllib.request.urlopen(f"{peer_url}/events?after={after}&limit={limit}", timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        hint = (" — the peer doesn't recognize this machine; check peer_host in its config.json "
                "matches this machine's tailnet name") if e.code == 403 else ""
        raise PeerError(f"peer answered HTTP {e.code}{hint}") from None
    except (urllib.error.URLError, OSError) as e:
        raise PeerError(f"peer unreachable at {peer_url}: {getattr(e, 'reason', e)}") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise PeerError(f"{peer_url} sent something that isn't JSON — is something other than orbitd "
                        "listening on that port?") from None
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        raise PeerError("peer response has no events list — are both machines running the same Orbit version?")
    return data


def validate_incoming(raw: object, peer: str) -> tuple[Event, str]:
    if not isinstance(raw, dict):
        raise ValueError("event is not a JSON object")
    if raw.get("origin") != peer:
        raise ValueError(f"origin {raw.get('origin')!r} is not the peer {peer!r}")
    seq = raw.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise ValueError(f"seq must be a positive whole number, got {seq!r}")
    t = raw.get("type")
    if not isinstance(t, str) or not TYPE_RE.match(t):
        raise ValueError(f"type {t!r} must look like '<capability>.<name>'")
    ts, v, data, keep = raw.get("ts"), raw.get("v", 1), raw.get("data"), raw.get("keep", "log")
    if not isinstance(ts, str):
        raise ValueError("ts must be a string")
    if not isinstance(v, int) or isinstance(v, bool) or v < 1:
        raise ValueError("v must be a whole number ≥ 1")
    if not isinstance(data, dict):
        raise ValueError("data must be a JSON object")
    if len(json.dumps(data, ensure_ascii=False).encode()) > MAX_DATA_BYTES:
        raise ValueError(f"data is larger than {MAX_DATA_BYTES} bytes")
    if keep not in KEEPS:
        raise ValueError(f"keep must be one of {KEEPS}, got {keep!r}")
    return Event(peer, seq, t, ts, v, data), keep


def pull_once(rt: loader.Runtime) -> bool:
    """Fetch everything new from the peer and dispatch `received`. True if the peer answered."""
    cfg, store = rt.cfg, rt.store
    received: list[Event] = []
    forgot = False
    try:
        while True:
            after = store.peer_cursor()
            page = fetch_events(cfg.peer_url, after)
            if new_installation(rt, page.get("instance")):
                if forgot:
                    raise PeerError(f"{cfg.peer_url} changed its instance id twice in one pull — "
                                    "is more than one orbitd answering on that address?")
                forgot = True
                continue  # forgotten; re-ask from seq 0
            highest = after
            for raw in page["events"]:
                seq = raw.get("seq") if isinstance(raw, dict) else None
                if isinstance(seq, int) and not isinstance(seq, bool):
                    highest = max(highest, seq)
                try:
                    event, keep = validate_incoming(raw, cfg.peer)
                except ValueError as e:
                    log(cfg.data_dir, "orbitd", f"skipped a bad event from {cfg.peer}: {e}")
                    continue
                if store.insert(event, keep):
                    received.append(event)
            if highest == after:
                break
            store.set_peer_cursor(highest)
            if not page.get("has_more"):
                break
    except PeerError as e:
        if store.get_meta("last_pull_error") != str(e):  # log each new kind of failure once
            log(cfg.data_dir, "orbitd", f"pull from {cfg.peer} failed: {e}")
            store.set_meta("last_pull_error", str(e))
        store.set_peer_status(False, None)
        dispatch_received(rt, received)
        return False
    store.delete_meta("last_pull_error")
    store.set_peer_status(True, now_iso())
    dispatch_received(rt, received)
    return True


def new_installation(rt: loader.Runtime, instance: object) -> bool:
    """True (after forgetting the peer's old events) if the peer's database changed.

    A reinstall, or a dev-mode database that once pretended to be the peer, restarts
    seqs at 1; without this, the old cursor and (origin, seq) rows would hide the new
    events. Peers that don't send an instance are never compared.
    """
    if not isinstance(instance, str) or not instance:
        return False
    store, peer = rt.store, rt.cfg.peer
    known = store.get_meta("peer_instance")
    store.set_meta("peer_instance", instance)
    if not known or known == instance:
        return False
    log(rt.cfg.data_dir, "orbitd", f"peer {peer} is a new installation (instance changed) — "
                                   "forgetting its old events and resyncing")
    store.forget_origin(peer)
    store.set_peer_cursor(0)
    return True


def dispatch_received(rt: loader.Runtime, events: list[Event]) -> bool:
    """Run `received` for each capability with matching `receives`. Pokes the peer if any emitted."""
    emitted = False
    for m in rt.manifests.values():
        if "received" not in m.triggers:
            continue
        matching = [e.to_dict() for e in events if e.type in m.receives]
        if matching:
            res = loader.invoke(rt, m, {"kind": "received", "events": matching})
            emitted = emitted or bool(res.output and res.output.emit)
    if emitted:
        poke_peer(rt.cfg)
    return emitted


def poke_peer(cfg: Config, timeout: float = 1.0) -> bool:
    """Tell the peer we have new events. Failures are fine: its 30 s pull catches up."""
    try:
        req = urllib.request.Request(f"{cfg.peer_url}/poke", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False
