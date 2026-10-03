"""`orbit <command>`: the entry point for people, bin/orbit, systemd and the shell snippet.

The core commands live here. Every other command belongs to a capability (see `orbit help`).
`greet` runs at every new shell, so it stays quiet on errors (the bashrc sends its stderr
to /dev/null), and the shell cuts it off after 1 s.
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from orbit import characters, config, loader, sync
from orbit.config import ConfigError
from orbit.contract import Output

CORE_COMMANDS = [
    ("greet", "show the login greeting"),
    ("help", "list commands"),
    ("doctor [--reset <capability>]", "check that everything works"),
    ("dev run|test|peer ...", "developer tools (run `orbit dev` for usage)"),
    ("daemon", "run orbitd (systemd does this for you)"),
    ("init --me <name> --peer <name> [--dev]", "write ~/.orbit/config.json"),
]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd, args = (argv[0], argv[1:]) if argv else ("help", [])
    if cmd == "init":
        return init(args)
    try:
        cfg = config.load()
    except ConfigError as e:
        print(f"orbit: {e}", file=sys.stderr)
        return 1
    if cmd == "daemon":
        from orbit import daemon
        return daemon.main(cfg)
    rt = loader.open_runtime(cfg)
    try:
        if cmd in ("help", "-h", "--help"):
            return show_help(rt)
        if cmd == "greet":
            return greet(rt)
        if cmd == "doctor":
            from orbit import doctor
            return doctor.main(rt, args)
        if cmd == "dev":
            from orbit import devtools
            return devtools.main(rt, args)
        m = rt.commands().get(cmd)
        if m is None:
            print(f"orbit: unknown command {cmd!r} — run `orbit help` to see what's available", file=sys.stderr)
            return 1
        return run_command(rt, m, cmd, args)
    finally:
        rt.store.close()


def use_color() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def show(out: Output) -> None:
    if out.print_text:
        print(out.print_text)
    if out.say:
        print(characters.render_says(out.say, color=use_color()))
    sys.stdout.flush()


def run_command(rt: loader.Runtime, m, name: str, args: list[str]) -> int:
    res = loader.run(rt, m, {"kind": "command", "name": name, "args": args})
    if res.output is None:
        print(f"orbit: {name} failed:\n{res.error}", file=sys.stderr)
        if res.stderr.strip():
            print(res.stderr.rstrip(), file=sys.stderr)
        return 1
    loader.apply(rt, m, res.output, "command")
    show(res.output)
    if res.output.emit:
        sync.poke_peer(rt.cfg)
    return 0


def greet(rt: loader.Runtime) -> int:
    ms = [m for _, m in sorted(rt.manifests.items()) if "login" in m.triggers]
    if not ms:
        return 0
    with ThreadPoolExecutor(max_workers=len(ms)) as pool:
        results = list(pool.map(lambda m: loader.run(rt, m, {"kind": "login"}), ms))
    says, emitted = [], False
    for m, res in zip(ms, results):
        if res.output is None:
            continue
        loader.apply(rt, m, res.output, "login")
        says.extend(res.output.say)
        emitted = emitted or bool(res.output.emit)
    if says:
        print(characters.render_says(says, color=use_color()))
        sys.stdout.flush()  # print before poking, in case the shell's 1 s timeout cuts us off
    if emitted:
        sync.poke_peer(rt.cfg)
    return 0


def show_help(rt: loader.Runtime) -> int:
    print("orbit — Pluto & Charon\n\ncore commands:")
    for usage, text in CORE_COMMANDS:
        print(f"  orbit {usage:<40} {text}")
    commands = rt.commands()
    if commands:
        print("\ncapability commands:")
        for name in sorted(commands):
            m = commands[name]
            c = next(c for c in m.commands if c.name == name)
            print(f"  orbit {c.usage:<40} {c.help}  [{m.name}]")
    if rt.problems:
        print(f"\n{len(rt.problems)} capability problem(s) — run `orbit doctor`")
    return 0


def init(args: list[str]) -> int:
    p = argparse.ArgumentParser(prog="orbit init", description="Write ~/.orbit/config.json")
    p.add_argument("--me", required=True, choices=config.CHARACTERS)
    p.add_argument("--peer", required=True, choices=config.CHARACTERS)
    p.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    p.add_argument("--dev", action="store_true", help="local testing against `orbit dev peer` (loopback only)")
    p.add_argument("--force", action="store_true", help="overwrite an existing config")
    a = p.parse_args(args)
    directory = config.data_dir()
    path = directory / "config.json"
    if path.exists() and not a.force:
        print(f"orbit: {path} already exists — pass --force to overwrite it", file=sys.stderr)
        return 1
    if a.me == a.peer:
        print("orbit: --me and --peer must be different machines", file=sys.stderr)
        return 1
    values: dict = {"me": a.me, "peer": a.peer, "port": a.port}
    if a.dev:
        values.update(bind="127.0.0.1", peer_url=f"http://127.0.0.1:{config.DEV_PEER_PORT}",
                      dev_allow_ips=["127.0.0.1"])
    print(f"wrote {config.write(directory, values)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
