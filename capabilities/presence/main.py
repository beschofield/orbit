#!/usr/bin/env python3
"""presence — shows the other person's state in your prompt, e.g. "♇ pluto: active".

tick (every 60 s): work out my own state from terminal idle time (/dev/pts atimes), and emit
presence.status (keep: latest) only when it changes. `orbit away [message]` sets a
manual state that sticks until `orbit back`.
tick and received: rebuild the prompt from the peer's latest status. The text comes
from the other machine, so control characters are stripped.
Contract: docs/capability-contract.md
"""
from __future__ import annotations

import json
import os
import sys
import time

SYMBOL = {"pluto": "♇", "charon": "☾"}
MAX_PROMPT = 40
MAX_MESSAGE = 30


def idle_minutes(pts_dir: str = "/dev/pts", uid: int | None = None,
                 now: float | None = None) -> int | None:
    """Least idle time across my terminals, in whole minutes; None when I have none.

    Like `who`, idle is how long since a tty was last used (its atime). Reading
    /dev/pts directly avoids `who`'s locale-dependent columns and also counts tmux panes.
    """
    uid = os.getuid() if uid is None else uid
    now = time.time() if now is None else now
    try:
        names = os.listdir(pts_dir)
    except OSError:
        return None
    found = []
    for name in names:
        if name == "ptmx":
            continue
        try:
            st = os.stat(os.path.join(pts_dir, name))
        except OSError:
            continue
        if st.st_uid == uid:
            found.append(max(0, int((now - st.st_atime) // 60)))
    return min(found) if found else None


def state_for(minutes: int | None) -> str:
    if minutes is None or minutes >= 60:
        return "away"
    return "active" if minutes < 5 else "idle"


def printable(value: object) -> str:
    return "".join(ch for ch in str(value) if ch.isprintable())


def prompt_text(inp: dict) -> str:
    peer = inp["peer"]
    name = peer["name"]
    symbol = SYMBOL.get(name, "*")
    if not peer["online"]:
        return f"{symbol} {name}: 💤"
    status = inp["latest"].get(name, {}).get("presence.status")
    if not status:
        return f"{symbol} {name}"
    data = status["data"]
    text = f"{symbol} {name}: {printable(data.get('state', '?'))}"
    if data.get("message"):
        text += f" ({printable(data['message'])})"
    return text if len(text) <= MAX_PROMPT else text[: MAX_PROMPT - 1] + "…"


def status_event(state: str, manual: bool, message: str | None = None) -> dict:
    data: dict = {"state": state, "manual": manual}
    if message:
        data["message"] = message
    return {"type": "presence.status", "data": data}


def tick(inp: dict, idle: int | None = None) -> dict:
    """`idle` (minutes) lets tests skip reading /dev/pts."""
    out: dict = {"prompt": prompt_text(inp)}
    mine = inp["latest"].get(inp["me"]["name"], {}).get("presence.status")
    if mine and mine["data"].get("manual"):
        return out
    state = state_for(idle_minutes() if idle is None else idle)
    if not mine or mine["data"].get("state") != state:
        out["emit"] = [status_event(state, False)]
    return out


def handle(inp: dict) -> dict:
    trigger = inp["trigger"]
    if trigger["kind"] == "command" and trigger["name"] == "away":
        message = printable(" ".join(trigger["args"]).strip())[:MAX_MESSAGE]
        return {"emit": [status_event("away", True, message or None)],
                "print": f"You're away{': ' + message if message else ''}. Run `orbit back` when you return."}
    if trigger["kind"] == "command" and trigger["name"] == "back":
        return {"emit": [status_event("active", False)], "print": "Welcome back!"}
    if trigger["kind"] == "tick":
        return tick(inp)
    if trigger["kind"] == "received":
        return {"prompt": prompt_text(inp)}
    return {}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout, ensure_ascii=False)
