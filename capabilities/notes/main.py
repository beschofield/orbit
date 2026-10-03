#!/usr/bin/env python3
"""notes — leave little notes for each other.

`orbit note <text>` emits notes.sent; the other machine shows it at its next login.
At login, unread notes are said by the sender's character, then marked notes.seen.
The sender then gets a read receipt at their next login (marked notes.receipts_shown).
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


def send(inp: dict, args: list[str]) -> dict:
    text = " ".join(args).strip()
    if not text:
        return {"print": 'usage: orbit note <text>    e.g. orbit note "lunch at 1?"'}
    if len(text) > MAX_NOTE:
        return {"print": f"Notes can be at most {MAX_NOTE} characters (yours is {len(text)})."}
    return {"emit": [{"type": "notes.sent", "data": {"text": text}}],
            "say": [{"who": inp["me"]["name"], "mood": "happy",
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
    notes = unread(inp)
    for e in notes[:MAX_SHOWN]:
        say.append({"who": peer, "mood": "love", "text": _text(e)})
    if len(notes) > MAX_SHOWN:
        say.append({"who": peer, "mood": "happy",
                    "text": f"…and {len(notes) - MAX_SHOWN} more. See them all with: orbit notes"})
    if notes:
        emit.append({"type": "notes.seen", "data": {"seqs": [e["seq"] for e in notes]}})
    receipts = new_receipts(inp)
    if receipts:
        what = "your note" if len(receipts) == 1 else f"your {len(receipts)} notes"
        say.append({"who": me, "mood": "happy", "text": f"{NAMES[peer]} read {what} ♥"})
        emit.append({"type": "notes.receipts_shown", "data": {"seqs": receipts}})
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
