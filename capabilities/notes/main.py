#!/usr/bin/env python3
"""notes — leave little notes for each other.

`orbit note <text>` emits notes.sent; the other machine shows it at its next login.
At login, unread notes are said by the sender's character, with a "✉ Note from …" header
and the time it was sent, then marked notes.seen.
The sender then gets a read receipt at their next login (marked notes.receipts_shown).
Bubbles that pass a note between the planets (sent, and each delivered note) look to the side,
toward the other planet; the read receipt is news for you, so it faces forward (no "look").
Unread and seen are worked out from input["events"] every time; there are no local files.
Contract: docs/capability-contract.md
"""
from __future__ import annotations

import datetime as dt
import json
import sys

MAX_NOTE = 280  # the speech-bubble limit, so a note always fits in one bubble
MAX_SHOWN = 5   # notes said at one login; the rest are summarized
NAMES = {"pluto": "Pluto", "charon": "Charon"}


def _seqs(events: list[dict], origin: str, type_: str) -> set[int]:
    return {s for e in events if e["origin"] == origin and e["type"] == type_
            for s in e["data"].get("seqs", []) if isinstance(s, int)}


def _text(e: dict) -> str:
    text = e["data"].get("text")
    return text[:MAX_NOTE] if isinstance(text, str) and text.strip() else "(empty note)"


def unread(inp: dict) -> list[dict]:
    me, peer = inp["me"]["name"], inp["peer"]["name"]
    seen = _seqs(inp["events"], me, "notes.seen")
    return [e for e in inp["events"] if e["origin"] == peer and e["type"] == "notes.sent" and e["seq"] not in seen]


def new_receipts(inp: dict) -> list[int]:
    me, peer = inp["me"]["name"], inp["peer"]["name"]
    mine = {e["seq"] for e in inp["events"] if e["origin"] == me and e["type"] == "notes.sent"}
    seen_by_peer = _seqs(inp["events"], peer, "notes.seen")
    return sorted((mine & seen_by_peer) - _seqs(inp["events"], me, "notes.receipts_shown"))


def unread_prompt(inp: dict) -> str:
    n = len(unread(inp))
    return f"✉ {n}" if n else ""


def _local(ts: str) -> str:
    try:
        return dt.datetime.fromisoformat(ts).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return ts


def _when(ts: str, now: str) -> str:
    """"1:05 pm" for today, "Oct 2, 1:05 pm" otherwise, in local time."""
    try:
        t = dt.datetime.fromisoformat(ts).astimezone()
        today = dt.datetime.fromisoformat(now).astimezone().date()
    except ValueError:
        return ts
    clock = f"{t.hour % 12 or 12}:{t.minute:02d} {'am' if t.hour < 12 else 'pm'}"
    return clock if t.date() == today else f"{t:%b} {t.day}, {clock}"


def incoming(e: dict, inp: dict) -> str:
    """A note as shown at login: a header saying who it's from and when, then the note."""
    header = f"✉ Note from {NAMES.get(e['origin'], e['origin'])} · {_when(e['ts'], inp['now'])}"
    body = _text(e)
    room = MAX_NOTE - len(header) - 1
    if len(body) > room:
        body = body[: room - 1] + "…"
    return f"{header}\n{body}"


def receipt_text(peer: str, seqs: list[int], inp: dict) -> str:
    if len(seqs) > 1:
        return f"{NAMES[peer]} read your {len(seqs)} notes ♥"
    mine = next((e for e in inp["events"] if e["origin"] == inp["me"]["name"]
                 and e["type"] == "notes.sent" and e["seq"] == seqs[0]), None)
    if mine is None:
        return f"{NAMES[peer]} read your note ♥"
    quote = _text(mine)
    if len(quote) > 40:
        quote = quote[:39] + "…"
    return f'{NAMES[peer]} read your note "{quote}" ♥'


def send(inp: dict, args: list[str]) -> dict:
    text = " ".join(args).strip()
    if not text:
        return {"print": 'usage: orbit note <text>    e.g. orbit note "lunch at 1?"'}
    if len(text) > MAX_NOTE:
        return {"print": f"Notes can be at most {MAX_NOTE} characters (yours is {len(text)})."}
    return {"emit": [{"type": "notes.sent", "data": {"text": text}}],
            "say": [{"who": inp["me"]["name"], "mood": "happy", "look": "side",
                     "text": f"Sent! I'll make sure {NAMES[inp['peer']['name']]} gets it."}]}


def history(inp: dict) -> dict:
    notes = [e for e in inp["events"] if e["type"] == "notes.sent"][-20:]
    if not notes:
        return {"print": "No notes yet. Send one with: orbit note <text>"}
    return {"print": "\n".join(f"{_local(e['ts'])}  {NAMES.get(e['origin'], e['origin'])}: {_text(e)}"
                               for e in notes)}


def login(inp: dict) -> dict:
    me, peer = inp["me"]["name"], inp["peer"]["name"]
    say: list[dict] = []
    emit: list[dict] = []
    receipts = new_receipts(inp)
    if receipts:  # first, so news about your notes isn't mixed up with hers
        say.append({"who": me, "mood": "happy", "text": receipt_text(peer, receipts, inp)})
        emit.append({"type": "notes.receipts_shown", "data": {"seqs": receipts}})
    notes = unread(inp)
    for e in notes[:MAX_SHOWN]:
        say.append({"who": peer, "mood": "love", "look": "side", "text": incoming(e, inp)})
    if len(notes) > MAX_SHOWN:
        say.append({"who": peer, "mood": "happy", "look": "side",
                    "text": f"…and {len(notes) - MAX_SHOWN} more. See them all with: orbit notes"})
    if notes:
        emit.append({"type": "notes.seen", "data": {"seqs": [e["seq"] for e in notes]}})
    return {"say": say, "emit": emit, "prompt": ""}


def handle(inp: dict) -> dict:
    trigger = inp["trigger"]
    if trigger["kind"] == "command":
        return send(inp, trigger["args"]) if trigger["name"] == "note" else history(inp)
    if trigger["kind"] == "login":
        return login(inp)
    if trigger["kind"] == "received":
        return {"prompt": unread_prompt(inp)}
    return {}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout, ensure_ascii=False)
