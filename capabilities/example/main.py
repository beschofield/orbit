#!/usr/bin/env python3
"""example — the template for new capabilities. Copy this whole folder to start one:

    cp -r capabilities/example capabilities/<your_name>

then follow .claude/skills/new-capability/SKILL.md. The rules are in
docs/capability-contract.md.

What this one does: `orbit hello [name]` prints a line, and your character says hi.
"""
import json
import sys


def handle(inp: dict) -> dict:
    """Turn one input (the contract's "Input") into one output (its "Output")."""
    trigger = inp["trigger"]

    # The core only sends commands listed in manifest.json "commands".
    if trigger["kind"] == "command" and trigger["name"] == "hello":
        name = " ".join(trigger["args"]) or "friend"
        return {
            # "print": plain text for whoever ran the command.
            "print": f"hello, {name}!",
            # "say": speech bubbles. Use your own machine's character (inp["me"]["name"])
            # unless the words come from the other person. Bubbles look forward, at the
            # person at the terminal. Add "look": "side" to make the planet look toward the
            # other one instead: do that when the bubble carries the other person's words
            # or reaches toward them (notes does it for sent and delivered notes).
            "say": [{"who": inp["me"]["name"], "mood": "happy",
                     "text": f"Hi {name}! I'm a brand-new capability."}],
            # Other keys you can return:
            #   "emit":   [{"type": "example.something", "data": {...}}] records an event.
            #             The type must be declared in manifest.json "event_types". It syncs
            #             to the other machine and shows up in inp["events"] later.
            #   "prompt": "short text" sets your piece of the shell prompt ("" clears it).
        }

    # A trigger we don't care about: do nothing.
    return {}


if __name__ == "__main__":
    # One JSON object in on stdin, one JSON object out on stdout.
    # To debug, use print(..., file=sys.stderr). stdout must contain only the JSON.
    json.dump(handle(json.load(sys.stdin)), sys.stdout, ensure_ascii=False)
