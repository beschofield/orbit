"""The capability contract, enforced.

docs/capability-contract.md is the readable version. This module and that doc must
agree; tests/test_contract_doc.py validates every example in the doc against this code.
Errors are collected (not raised one at a time) so one run shows every fix needed.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

CONTRACT_VERSION = 1
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
COMMAND_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}\.[a-z][a-z0-9_.]{0,60}$")
WHO = ("pluto", "charon")
MOODS = ("neutral", "happy", "sleepy", "love", "thinking", "worried")
LOOKS = ("forward", "side")  # forward: at the person at the terminal; side: toward the other planet
TRIGGERS = ("login", "tick", "received")
KEEPS = ("log", "latest")
RESERVED_COMMANDS = ("daemon", "dev", "doctor", "greet", "help", "init", "update")
OUTPUT_KEYS = ("say", "emit", "prompt", "print")
MAX_SAY_CHARS = 280
MAX_PROMPT_CHARS = 40
MAX_DATA_BYTES = 16 * 1024
MIN_TICK_SECONDS = 10

Bad = Callable[[str, str], None]


class ContractError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Command:
    name: str
    usage: str
    help: str


@dataclass(frozen=True)
class Manifest:
    name: str
    description: str
    run: Path
    commands: tuple[Command, ...]
    triggers: tuple[str, ...]
    tick_seconds: int | None
    event_types: dict[str, str]  # event type -> "log" | "latest"
    receives: tuple[str, ...]
    dir: Path


@dataclass(frozen=True)
class Say:
    who: str
    mood: str
    text: str
    # Which way the planet looks. Last, with a default, so Say(who, mood, text) still works
    # and a capability that leaves "look" out gets forward.
    look: str = "forward"


@dataclass(frozen=True)
class Emit:
    type: str
    data: dict
    v: int


@dataclass(frozen=True)
class Output:
    say: tuple[Say, ...] = ()
    emit: tuple[Emit, ...] = ()
    prompt: str | None = None      # None = leave this capability's prompt segment unchanged
    print_text: str | None = None  # the JSON key is "print"


# ---------- manifest ----------

def parse_manifest(path: Path) -> Manifest:
    source = str(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ContractError([f"{source}: missing — every capability needs one "
                             "(copy capabilities/example/manifest.json)"]) from None
    except json.JSONDecodeError as e:
        raise ContractError([f"{source}: invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}"]) from None
    return manifest_from_dict(data, path.parent, source)


def manifest_from_dict(data: object, directory: Path, source: str, check_files: bool = True) -> Manifest:
    problems: list[str] = []

    def bad(where: str, msg: str) -> None:
        problems.append(f"{source}: {where}: {msg}")

    if not isinstance(data, dict):
        raise ContractError([f"{source}: must be a JSON object"])

    name = data.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        bad("name", 'must be 2-31 lowercase letters, digits or _, starting with a letter, e.g. "notes"')
        name = "?"
    elif check_files and directory.name != name:
        bad("name", f'is "{name}" but the folder is "{directory.name}" — make them match')

    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        bad("description", "must be a non-empty string")

    if data.get("contract") != CONTRACT_VERSION:
        bad("contract", f"must be {CONTRACT_VERSION}")

    run = data.get("run")
    if not isinstance(run, str) or not run or "/" in run:
        bad("run", 'must be a file name inside the capability folder, e.g. "main.py"')
        run = "?"
    elif check_files:
        path = directory / run
        if not path.is_file():
            bad("run", f"{path} does not exist")
        elif not os.access(path, os.X_OK):
            bad("run", f"{path} is not executable — run: chmod +x {path}")

    commands = _commands(data.get("commands", []), bad)
    triggers = _triggers(data.get("triggers", []), bad)
    tick = data.get("tick_seconds")
    if "tick" in triggers:
        if not isinstance(tick, int) or isinstance(tick, bool) or tick < MIN_TICK_SECONDS:
            bad("tick_seconds", f'must be a whole number ≥ {MIN_TICK_SECONDS} when triggers includes "tick"')
    elif tick is not None:
        bad("tick_seconds", 'must be null unless triggers includes "tick"')
    event_types = _event_types(data.get("event_types", {}), name, bad)
    receives = _receives(data.get("receives", []), triggers, bad)

    if problems:
        raise ContractError(problems)
    return Manifest(name=name, description=description, run=directory / run, commands=commands,
                    triggers=triggers, tick_seconds=tick if "tick" in triggers else None,
                    event_types=event_types, receives=receives, dir=directory)


def _commands(raw: object, bad: Bad) -> tuple[Command, ...]:
    if not isinstance(raw, list):
        bad("commands", "must be a list")
        return ()
    out = []
    for i, c in enumerate(raw):
        where = f"commands[{i}]"
        if not isinstance(c, dict):
            bad(where, "must be an object with name, usage and help")
            continue
        name = c.get("name")
        if not isinstance(name, str) or not COMMAND_RE.match(name):
            bad(f"{where}.name", 'must be lowercase letters, digits or -, e.g. "note"')
            continue
        if name in RESERVED_COMMANDS:
            bad(f"{where}.name", f'"{name}" is reserved by the core — pick another name')
            continue
        ok = True
        for key in ("usage", "help"):
            if not isinstance(c.get(key), str) or not c[key].strip():
                bad(f"{where}.{key}", "must be a non-empty string")
                ok = False
        if ok:
            out.append(Command(name, c["usage"], c["help"]))
    return tuple(out)


def _triggers(raw: object, bad: Bad) -> tuple[str, ...]:
    if not isinstance(raw, list):
        bad("triggers", "must be a list")
        return ()
    out = []
    for i, t in enumerate(raw):
        if t == "command":
            bad(f"triggers[{i}]", '"command" is implied by "commands" — remove it')
        elif t not in TRIGGERS:
            bad(f"triggers[{i}]", f"{json.dumps(t)} is not a trigger — use one of: {', '.join(TRIGGERS)}")
        else:
            out.append(t)
    return tuple(out)


def _event_types(raw: object, name: str, bad: Bad) -> dict[str, str]:
    if not isinstance(raw, dict):
        bad("event_types", 'must be an object like {"notes.sent": {"keep": "log"}}')
        return {}
    out = {}
    for t, spec in raw.items():
        where = f'event_types."{t}"'
        if not t.startswith(f"{name}."):
            bad(where, f'must start with "{name}." — rename to "{name}.{t.split(".", 1)[-1]}"')
            continue
        if not TYPE_RE.match(t):
            bad(where, "use lowercase letters, digits, _ and . only")
            continue
        keep = spec.get("keep") if isinstance(spec, dict) else None
        if keep not in KEEPS:
            bad(f"{where}.keep", 'must be "log" or "latest"')
            continue
        out[t] = keep
    return out


def _receives(raw: object, triggers: tuple[str, ...], bad: Bad) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(t, str) and TYPE_RE.match(t) for t in raw):
        bad("receives", 'must be a list of event types like "notes.sent"')
        return ()
    if raw and "received" not in triggers:
        bad("receives", 'is set but triggers lacks "received" — add it')
    if "received" in triggers and not raw:
        bad("receives", 'is empty but triggers includes "received" — list the event types to react to')
    return tuple(raw)


# ---------- output ----------

def parse_output(stdout: str, manifest: Manifest) -> Output:
    source = f"{manifest.name} output"
    if not stdout.strip():
        return Output()
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise ContractError([f"{source}: stdout is not one JSON object ({e.msg}, line {e.lineno}) — "
                             "print only the JSON result to stdout and send debug output to stderr"]) from None
    return output_from_dict(data, manifest, source)


def output_from_dict(data: object, manifest: Manifest, source: str) -> Output:
    problems: list[str] = []

    def bad(where: str, msg: str) -> None:
        problems.append(f"{source}: {where}: {msg}")

    if not isinstance(data, dict):
        raise ContractError([f"{source}: must be a JSON object, got {type(data).__name__}"])
    for key in data:
        if key not in OUTPUT_KEYS:
            bad(key, f"unknown key — allowed keys: {', '.join(OUTPUT_KEYS)}")
    says = _says(data.get("say", []), bad)
    emits = _emits(data.get("emit", []), manifest, bad)
    prompt = data.get("prompt")
    if prompt is not None:
        if not isinstance(prompt, str):
            bad("prompt", "must be a string (or leave it out)")
        elif len(prompt) > MAX_PROMPT_CHARS:
            bad("prompt", f"is {len(prompt)} characters; the limit is {MAX_PROMPT_CHARS}")
        elif not prompt.isprintable():
            bad("prompt", "must not contain newlines or control characters")
    printed = data.get("print")
    if printed is not None and not isinstance(printed, str):
        bad("print", "must be a string")
    if problems:
        raise ContractError(problems)
    return Output(say=says, emit=emits, prompt=prompt, print_text=printed)


def _says(raw: object, bad: Bad) -> tuple[Say, ...]:
    if not isinstance(raw, list):
        bad("say", "must be a list")
        return ()
    out = []
    for i, s in enumerate(raw):
        where = f"say[{i}]"
        if not isinstance(s, dict):
            bad(where, 'must be an object like {"who": "pluto", "mood": "happy", "text": "hi"}')
            continue
        ok = True
        if s.get("who") not in WHO:
            bad(f"{where}.who", 'must be "pluto" or "charon"')
            ok = False
        if s.get("mood") not in MOODS:
            bad(f"{where}.mood", f"must be one of: {', '.join(MOODS)}")
            ok = False
        look = s.get("look", "forward")
        if look not in LOOKS:
            bad(f"{where}.look", 'must be "forward" or "side" (leave it out for "forward")')
            ok = False
        text = s.get("text")
        if not isinstance(text, str) or not text.strip():
            bad(f"{where}.text", "must be a non-empty string")
            ok = False
        elif len(text) > MAX_SAY_CHARS:
            bad(f"{where}.text", f"is {len(text)} characters; the limit is {MAX_SAY_CHARS}")
            ok = False
        if ok:
            out.append(Say(s["who"], s["mood"], text, look))
    return tuple(out)


def _emits(raw: object, manifest: Manifest, bad: Bad) -> tuple[Emit, ...]:
    if not isinstance(raw, list):
        bad("emit", "must be a list")
        return ()
    out = []
    for i, e in enumerate(raw):
        where = f"emit[{i}]"
        if not isinstance(e, dict):
            bad(where, 'must be an object like {"type": "notes.sent", "data": {...}}')
            continue
        t, data, v = e.get("type"), e.get("data", {}), e.get("v", 1)
        ok = True
        if not isinstance(t, str) or t not in manifest.event_types:
            bad(f"{where}.type", f"{json.dumps(t)} is not declared in manifest.json event_types — add it there")
            ok = False
        if not isinstance(data, dict):
            bad(f"{where}.data", "must be a JSON object")
            ok = False
        elif len(json.dumps(data, ensure_ascii=False).encode()) > MAX_DATA_BYTES:
            bad(f"{where}.data", f"is larger than {MAX_DATA_BYTES} bytes — store less")
            ok = False
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            bad(f"{where}.v", "must be a whole number ≥ 1 (or leave it out for 1)")
            ok = False
        if ok:
            out.append(Emit(t, data, v))
    return tuple(out)


def _say_to_dict(s: Say) -> dict:
    """Leaves out look when it's forward, the same way capability authors write it, so test
    cases and `orbit dev run` output don't need "look": "forward" everywhere."""
    d = {"who": s.who, "mood": s.mood, "text": s.text}
    if s.look != "forward":
        d["look"] = s.look
    return d


def output_to_dict(out: Output) -> dict:
    """The comparable form of an Output, used by `orbit dev run` and test cases."""
    return {
        "say": [_say_to_dict(s) for s in out.say],
        "emit": [{"type": e.type, "data": e.data, "v": e.v} for e in out.emit],
        "prompt": out.prompt,
        "print": out.print_text,
    }
