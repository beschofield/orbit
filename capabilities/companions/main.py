#!/usr/bin/env python3
"""companions — the characters say hello.

login: a greeting from your own character that fits the local time of day, plus a
line when the other machine is offline. `orbit hi`: a friendly line.
Lines live in lines.json, so edit them freely. The choice depends on the minute of
`now`, so greetings vary while tests stay deterministic.
Contract: docs/capability-contract.md
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

LINES = json.loads((Path(__file__).parent / "lines.json").read_text(encoding="utf-8"))
NAMES = {"pluto": "Pluto", "charon": "Charon"}


def part_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def pick(kind: str, inp: dict) -> str:
    options = LINES[kind]
    minute = int(inp["now"][14:16])
    return options[minute % len(options)].format(peer=NAMES[inp["peer"]["name"]], me=NAMES[inp["me"]["name"]])


def handle(inp: dict) -> dict:
    me = inp["me"]["name"]
    trigger = inp["trigger"]
    if trigger["kind"] == "login":
        part = part_of_day(dt.datetime.fromisoformat(inp["now"]).astimezone().hour)
        say = [{"who": me, "mood": "sleepy" if part == "night" else "happy", "text": pick(part, inp)}]
        if not inp["peer"]["online"]:
            say.append({"who": me, "mood": "neutral", "text": pick("peer_asleep", inp)})
        return {"say": say}
    if trigger["kind"] == "command" and trigger["name"] == "hi":
        return {"say": [{"who": me, "mood": "happy", "text": pick("hi", inp)}]}
    return {}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout, ensure_ascii=False)
