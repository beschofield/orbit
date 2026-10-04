#!/usr/bin/env python3
"""notes — leave little notes for each other.

`orbit note <text>` emits notes.sent; the other machine shows it at its next login.
At login, unread notes are said by the sender's character, with a "✉ Note from …" header
and the time it was sent, then marked notes.seen.
The sender then gets a read receipt at their next login (marked notes.receipts_shown).
`orbit notes` lists recent notes, numbered, marking each of mine "✓ read" or
"· not read yet" (from the peer's notes.seen); `orbit read [n]` shows one again in its
sender's bubble (default: the newest one received), marking it seen if it wasn't.
`orbit unread` says every unread note at once. Login says at most MAX_SHOWN and leaves
the rest unread (still counted in the prompt) so `orbit unread` can show them later.
Bubbles that pass a note between the planets (sent, delivered, or shown again by
`orbit read`) look to the side, toward the other planet; the read receipt is news for
you, so it faces forward (no "look").
Unread and seen are worked out from input["events"] every time; there are no local files.
Contract: docs/capability-contract.md
"""
from __future__ import annotations

import datetime as dt
import json
import sys

MAX_NOTE = 280  # the speech-bubble limit, so a note always fits in one bubble
MAX_SHOWN = 5   # notes said at one login; the rest are summarized and stay unread
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
    return f"✉  {n}" if n else ""


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


def numbered(inp: dict) -> list[tuple[int, dict]]:
    """Every note in the input, numbered from 1 in arrival order: the numbers `orbit read` takes."""
    return list(enumerate((e for e in inp["events"] if e["type"] == "notes.sent"), start=1))


def history(inp: dict) -> dict:
    """The last 20 notes, numbered; each of mine ends with whether the peer has read it yet."""
    me, peer = inp["me"]["name"], inp["peer"]["name"]
    notes = numbered(inp)[-20:]
    if not notes:
        return {"print": "No notes yet. Send one with: orbit note <text>"}
    seen_by_peer = _seqs(inp["events"], peer, "notes.seen")
    width = len(str(notes[-1][0]))

    def line(n: int, e: dict) -> str:
        status = "" if e["origin"] != me else "  ✓ read" if e["seq"] in seen_by_peer else "  · not read yet"
        return f"{n:>{width}}  {_local(e['ts'])}  {NAMES.get(e['origin'], e['origin'])}: {_text(e)}{status}"
    return {"print": "\n".join(line(n, e) for n, e in notes)}


def read(inp: dict, args: list[str]) -> dict:
    """Show one note again, said by its sender as at login. Reading an unread note marks it seen."""
    peer = inp["peer"]["name"]
    notes = numbered(inp)
    if not args:
        received = [e for _, e in notes if e["origin"] == peer]
        if not received:
            return {"print": f"No notes from {NAMES[peer]} yet. See everything with: orbit notes"}
        note = received[-1]
    elif len(args) == 1 and args[0].isdigit():
        note = next((e for n, e in notes if n == int(args[0])), None)
        if note is None:
            return {"print": f"There's no note #{args[0]}. See the numbers with: orbit notes"}
    else:
        return {"print": f"usage: orbit read [n]    e.g. orbit read (newest from {NAMES[peer]}), "
                         "orbit read 3 (#3 in orbit notes)"}
    out: dict = {"say": [{"who": note["origin"], "mood": "love", "look": "side", "text": incoming(note, inp)}]}
    left = [e["seq"] for e in unread(inp)]
    if note["origin"] == peer and note["seq"] in left:
        out["emit"] = [{"type": "notes.seen", "data": {"seqs": [note["seq"]]}}]
        out["prompt"] = f"✉  {len(left) - 1}" if len(left) > 1 else ""
    return out


def say_unread(inp: dict) -> dict:
    """Say every unread note, oldest first, with no MAX_SHOWN limit, and mark them all seen."""
    notes = unread(inp)
    if not notes:
        return {"print": f"No unread notes from {NAMES[inp['peer']['name']]}. See everything with: orbit notes"}
    return {"say": [{"who": e["origin"], "mood": "love", "look": "side", "text": incoming(e, inp)} for e in notes],
            "emit": [{"type": "notes.seen", "data": {"seqs": [e["seq"] for e in notes]}}],
            "prompt": ""}


def login(inp: dict) -> dict:
    me, peer = inp["me"]["name"], inp["peer"]["name"]
    say: list[dict] = []
    emit: list[dict] = []
    receipts = new_receipts(inp)
    if receipts:  # first, so news about your notes isn't mixed up with hers
        say.append({"who": me, "mood": "happy", "text": receipt_text(peer, receipts, inp)})
        emit.append({"type": "notes.receipts_shown", "data": {"seqs": receipts}})
    waiting = unread(inp)
    notes, rest = waiting[:MAX_SHOWN], len(waiting) - MAX_SHOWN
    for e in notes:
        say.append({"who": peer, "mood": "love", "look": "side", "text": incoming(e, inp)})
    if rest > 0:  # left unread, so the prompt keeps counting them until `orbit unread`
        say.append({"who": peer, "mood": "happy", "look": "side",
                    "text": f"…and {rest} more. Read {'it' if rest == 1 else 'them'} with: orbit unread"})
    if notes:
        emit.append({"type": "notes.seen", "data": {"seqs": [e["seq"] for e in notes]}})
    return {"say": say, "emit": emit, "prompt": f"✉  {rest}" if rest > 0 else ""}


def handle(inp: dict) -> dict:
    trigger = inp["trigger"]
    if trigger["kind"] == "command":
        commands = {"note": send, "read": read, "notes": lambda inp, _: history(inp),
                    "unread": lambda inp, _: say_unread(inp)}
        return commands[trigger["name"]](inp, trigger["args"])
    if trigger["kind"] == "login":
        return login(inp)
    if trigger["kind"] == "received":
        return {"prompt": unread_prompt(inp)}
    return {}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout, ensure_ascii=False)
