"""`orbit dev ...`: ways to check work without touching real data.

run   one capability, once, with a real input built from this machine's store.
      Prints the input, output, problems and bubbles. Writes nothing.
test  runs capabilities/<name>/tests/*.json (see docs/capability-contract.md, "Tests").
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

from orbit import characters, config, contract, loader
from orbit.contract import Manifest

USAGE = """usage:
  orbit dev run <capability> <login|tick|received|command> [command-name] [args...]
  orbit dev test [capability...]
  orbit dev peer [command...]   (fake peer on loopback; see CLAUDE.md)"""

CASE_DEFAULTS = {
    "contract": 1,
    "me": {"name": "charon"},
    "peer": {"name": "pluto", "online": True, "last_seen": None},
    "now": "2026-10-03T14:00:00Z",
    "events": [],
    "latest": {"charon": {}, "pluto": {}},
}


def main(rt: loader.Runtime, args: list[str]) -> int:
    sub, rest = (args[0], args[1:]) if args else ("", [])
    if sub == "run":
        return dev_run(rt, rest)
    if sub == "test":
        return dev_test(rt, rest)
    if sub == "peer":
        return dev_peer(rt, rest)
    print(USAGE, file=sys.stderr)
    return 2


def dev_run(rt: loader.Runtime, args: list[str]) -> int:
    if len(args) < 2 or args[1] not in loader.TIMEOUTS:
        print(USAGE, file=sys.stderr)
        return 2
    m = rt.manifests.get(args[0])
    if m is None:
        print(f"orbit dev: no capability named {args[0]!r} — loaded: {', '.join(sorted(rt.manifests)) or 'none'}",
              file=sys.stderr)
        for p in rt.problems:
            print(p, file=sys.stderr)
        return 1
    kind = args[1]
    if kind == "command":
        if len(args) < 3:
            print("orbit dev run: a command trigger needs a command name, e.g. `orbit dev run notes command note hi`",
                  file=sys.stderr)
            return 2
        trigger = {"kind": "command", "name": args[2], "args": args[3:]}
    elif kind == "received":
        try:
            trigger = {"kind": "received", "events": json.loads(args[2]) if len(args) > 2 else []}
        except json.JSONDecodeError as e:
            print(f"orbit dev run: the received events must be a JSON list: {e}", file=sys.stderr)
            return 2
    else:
        trigger = {"kind": kind}
    payload = loader.build_input(rt, m, trigger)
    res = loader.execute(m, payload, loader.TIMEOUTS[kind])
    print("── input ──")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if res.stderr.strip():
        print("── stderr ──")
        print(res.stderr.rstrip())
    if res.output is None:
        print("── error ──")
        print(res.error)
        return 1
    print("── output ──")
    print(json.dumps(contract.output_to_dict(res.output), indent=2, ensure_ascii=False))
    if res.output.say:
        print("── rendered ──")
        print(characters.render_says(res.output.say))
        if kind in ("tick", "received"):
            print("note: say is ignored for tick/received triggers (they have no terminal)")
    return 0


def case_input(partial: dict) -> dict:
    merged = copy.deepcopy(CASE_DEFAULTS)
    merged.update(partial)
    return merged


def run_cases(m: Manifest) -> tuple[int, list[str]]:
    """Run every tests/*.json case. Returns (number of cases, failure messages)."""
    files = sorted((m.dir / "tests").glob("*.json"))
    failures: list[str] = []
    for f in files:
        try:
            case = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(f"{f}: invalid JSON: {e}")
            continue
        if not isinstance(case, dict) or "input" not in case or "expect" not in case:
            failures.append(f'{f}: must look like {{"input": {{...}}, "expect": {{...}}}}')
            continue
        res = loader.execute(m, case_input(case["input"]), 10.0, env={**os.environ, "TZ": "UTC"})
        if res.output is None:
            detail = f"\nstderr: {res.stderr.strip()}" if res.stderr.strip() else ""
            failures.append(f"{f}: {res.error}{detail}")
            continue
        actual = contract.output_to_dict(res.output)
        for key, want in case["expect"].items():
            if key not in actual:
                failures.append(f"{f}: expect.{key}: not an output key (use {', '.join(actual)})")
            elif actual[key] != want:
                failures.append(f"{f}: {key}:\n  expected {json.dumps(want, ensure_ascii=False)}\n"
                                f"  got      {json.dumps(actual[key], ensure_ascii=False)}")
    return len(files), failures


def dev_test(rt: loader.Runtime, names: list[str]) -> int:
    failed = False
    for name in names or sorted(rt.manifests):
        m = rt.manifests.get(name)
        if m is None:
            print(f"✗ {name}: not loaded (see `orbit doctor`)")
            failed = True
            continue
        count, failures = run_cases(m)
        if count == 0:
            print(f"✗ {name}: no test cases in {m.dir / 'tests'} — add at least one")
            failed = True
        elif failures:
            print(f"✗ {name}: {len(failures)} failing")
            for line in failures:
                print("  " + line.replace("\n", "\n  "))
            failed = True
        else:
            print(f"✓ {name}: {count} cases pass")
    for p in rt.problems:
        print(f"✗ {p}")
    return 1 if failed or rt.problems else 0


def devpeer_dir() -> Path:
    env = os.environ.get("ORBIT_DEVPEER_DIR")
    return Path(env) if env else Path.home() / ".orbit-devpeer"


def dev_peer(rt: loader.Runtime, args: list[str]) -> int:
    """With no args: run a fake peer daemon on loopback. With args: run `orbit <args>` as that peer."""
    d = devpeer_dir()
    if not (d / "config.json").exists():
        config.write(d, {"me": rt.cfg.peer, "peer": rt.cfg.me, "port": config.DEV_PEER_PORT, "bind": "127.0.0.1",
                         "peer_url": f"http://127.0.0.1:{rt.cfg.port}", "dev_allow_ips": ["127.0.0.1"],
                         "capabilities_dir": str(rt.cfg.capabilities_dir)})
    if not args:
        print(f"fake {rt.cfg.peer}: listening on 127.0.0.1:{config.DEV_PEER_PORT}, data in {d}. Ctrl-C stops it.")
        print(f'try, in another terminal:  orbit dev peer note "hi from the fake {rt.cfg.peer}"')
        if rt.cfg.peer_url != f"http://127.0.0.1:{config.DEV_PEER_PORT}":
            print(f"note: this machine talks to {rt.cfg.peer_url}, not the fake peer. Point it here with "
                  f"`orbit init --dev --force --me {rt.cfg.me} --peer {rt.cfg.peer}` "
                  f"(and back later with `orbit init --force --me {rt.cfg.me} --peer {rt.cfg.peer}`)")
    sys.stdout.flush()
    env = {**os.environ, "ORBIT_DIR": str(d)}
    try:
        return subprocess.call([sys.executable, "-m", "orbit.cli", *(args or ["daemon"])],
                               env=env, cwd=config.REPO_ROOT)
    except KeyboardInterrupt:
        return 0
