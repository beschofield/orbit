#!/usr/bin/env python3
"""presence — shows the other person's state in your prompt, e.g. "♇ pluto: active".

tick (every 60 s): work out my own state from terminal idle time (/dev/pts atimes), and emit
presence.status (keep: latest) only when it changes. `orbit away [message]` sets a
manual state that sticks until `orbit back`.
tick and received: rebuild the prompt from the peer's latest status. The text comes
from the other machine, so control characters are stripped.
`orbit status toggle|on|off` hides or shows the segment. The choice is a presence.display
event (keep: latest), because capabilities keep no state of their own. Hiding only
affects my prompt: my own status keeps going to the peer.
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
# The prompt shows states as emoji; the event keeps the word, so an older install
# still shows something sensible. Unknown states fall back to the word.
EMOJI = {"active": "✨", "idle": "💭", "away": "⏳"}
STYLES = ("both", "symbol", "name")
DEFAULT_STYLE = "both"
USAGE = "usage: orbit status toggle|on|off\n       orbit status style both|symbol|name"


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


def label(name: str, style: str) -> str:
    """Who the segment is about: "♇ pluto" (both), "♇" (symbol) or "pluto" (name)."""
    symbol = SYMBOL.get(name, "*")
    return {"symbol": symbol, "name": name}.get(style, f"{symbol} {name}")


def with_state(name: str, style: str, state: str) -> str:
    """Label plus state: "♇ pluto: ✨", "♇ ✨" or "pluto: ✨" (a lone symbol reads better without the colon)."""
    return f"{label(name, style)}{' ' if style == 'symbol' else ': '}{state}"


def prompt_text(inp: dict, style: str = DEFAULT_STYLE) -> str:
    peer = inp["peer"]
    name = peer["name"]
    if not peer["online"]:
        return with_state(name, style, "💤")
    status = inp["latest"].get(name, {}).get("presence.status")
    if not status:
        return label(name, style)
    data = status["data"]
    state = printable(data.get("state", "?"))
    text = with_state(name, style, EMOJI.get(state, state))
    if data.get("message"):
        text += f" ({printable(data['message'])})"
    return text if len(text) <= MAX_PROMPT else text[: MAX_PROMPT - 1] + "…"


def display(inp: dict) -> dict:
    """My prompt settings, {shown, style}. No presence.display event yet means shown, both."""
    event = inp["latest"].get(inp["me"]["name"], {}).get("presence.display")
    data = event["data"] if event else {}
    style = data.get("style")
    return {"shown": data.get("shown", True) is not False,
            "style": style if style in STYLES else DEFAULT_STYLE}


def prompt_segment(inp: dict) -> str:
    settings = display(inp)
    return prompt_text(inp, settings["style"]) if settings["shown"] else ""


def status_command(inp: dict, args: list[str]) -> dict:
    """`orbit status toggle|on|off` hides or shows; `orbit status style <style>` picks the look.

    Bare `orbit status` only prints usage: it reads like "show me the status", so
    silently hiding the segment would surprise people. Each event carries both
    settings, so changing one keeps the other.
    """
    words = [a.lower() for a in args]
    settings = display(inp)
    if words in (["toggle"], ["on"], ["off"]):
        settings["shown"] = not settings["shown"] if words[0] == "toggle" else words[0] == "on"
        message = ("Status is back in your prompt." if settings["shown"]
                   else "Status hidden from your prompt. Run `orbit status on` to show it again.")
    elif len(words) == 2 and words[0] == "style" and words[1] in STYLES:
        settings["style"] = words[1]
        message = f"Status style: {words[1]}, e.g. {with_state(inp['peer']['name'], words[1], EMOJI['active'])}"
        if not settings["shown"]:
            message += ". It's hidden right now; run `orbit status on` to see it."
    else:
        return {"print": USAGE}
    return {"emit": [{"type": "presence.display", "data": settings}],
            "prompt": prompt_text(inp, settings["style"]) if settings["shown"] else "",
            "print": message}


def status_event(state: str, manual: bool, message: str | None = None) -> dict:
    data: dict = {"state": state, "manual": manual}
    if message:
        data["message"] = message
    return {"type": "presence.status", "data": data}


def tick(inp: dict, idle: int | None = None) -> dict:
    """`idle` (minutes) lets tests skip reading /dev/pts."""
    out: dict = {"prompt": prompt_segment(inp)}
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
    if trigger["kind"] == "command" and trigger["name"] == "status":
        return status_command(inp, trigger["args"])
    if trigger["kind"] == "tick":
        return tick(inp)
    if trigger["kind"] == "received":
        return {"prompt": prompt_segment(inp)}
    return {}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout, ensure_ascii=False)
