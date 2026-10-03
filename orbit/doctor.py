"""`orbit doctor`: one command that says what works, what doesn't, and how to fix it."""
from __future__ import annotations

import sys
from typing import Iterator

from orbit import CORE_VERSION, daemon, loader, sync


def main(rt: loader.Runtime, args: list[str]) -> int:
    if args and args[0] == "--reset":
        if len(args) < 2:
            print("usage: orbit doctor --reset <capability>", file=sys.stderr)
            return 2
        for name in args[1:]:
            loader.reset(rt, name)
            print(f"reset {name} — it will run again")
        return 0
    all_ok = True
    for ok, message in checks(rt):
        print(f"{'✓' if ok else '✗'} {message}")
        all_ok = all_ok and ok
    return 0 if all_ok else 1


def checks(rt: loader.Runtime) -> Iterator[tuple[bool, str]]:
    cfg = rt.cfg
    yield True, f"config: this is {cfg.me}; peer {cfg.peer} at {cfg.peer_url}"
    for problem in rt.problems:
        yield False, problem
    yield True, f"capabilities loaded: {', '.join(sorted(rt.manifests)) or 'none'}"
    for name, m in sorted(rt.manifests.items()):
        if loader.is_disabled(rt, m):
            yield False, (f"{name} is disabled after repeated failures — read {cfg.data_dir}/logs/{name}.log, "
                          f"fix it, then `orbit doctor --reset {name}`")

    try:
        host = daemon.resolve_bind(cfg)
    except daemon.DaemonError as e:
        yield False, str(e)
        host = None
    if host:
        mine = sync.get_json(f"http://{host}:{cfg.port}/health")
        if mine and mine.get("me") == cfg.me:
            yield True, f"orbitd is running on {host}:{cfg.port}"
            running, on_disk = set(mine.get("capabilities", [])), set(rt.manifests)
            if running != on_disk:
                details = [f"orbitd hasn't loaded: {', '.join(sorted(on_disk - running))}" if on_disk - running else "",
                           f"orbitd still runs removed: {', '.join(sorted(running - on_disk))}"
                           if running - on_disk else ""]
                yield False, (f"{'; '.join(d for d in details if d)} — it rescans every 30 s; if this persists, "
                              "`systemctl --user restart orbitd`")
        else:
            yield False, (f"orbitd is not answering on {host}:{cfg.port} — try `systemctl --user status orbitd` "
                          f"and {cfg.data_dir}/logs/orbitd.log")

    theirs = sync.get_json(f"{cfg.peer_url}/health")
    if theirs is None:
        yield False, (f"{cfg.peer} is not answering at {cfg.peer_url} (fine if it's switched off; otherwise check "
                      f"orbitd there and that the tailnet allows port {cfg.port})")
        return
    if theirs.get("me") != cfg.peer:
        yield False, (f"peer_url points at {theirs.get('me')}, expected {cfg.peer} — fix peer_url (or peer_host) "
                      f"in {cfg.data_dir}/config.json")
        return
    yield True, f"{cfg.peer} is up (core {theirs.get('core_version')})"
    if theirs.get("core_version") != CORE_VERSION:
        yield False, (f"core versions differ: {cfg.me} has {CORE_VERSION}, {cfg.peer} has "
                      f"{theirs.get('core_version')} — update both machines")
    mine_caps, their_caps = set(rt.manifests), set(theirs.get("capabilities", []))
    if mine_caps - their_caps:
        yield False, f"only on {cfg.me}: {', '.join(sorted(mine_caps - their_caps))} — install it on {cfg.peer} too"
    if their_caps - mine_caps:
        yield False, f"only on {cfg.peer}: {', '.join(sorted(their_caps - mine_caps))} — install it on {cfg.me} too"
    try:
        sync.fetch_events(cfg.peer_url, rt.store.peer_cursor(), limit=1)
        yield True, f"{cfg.peer} accepts requests from {cfg.me}"
    except sync.PeerError as e:
        yield False, f"{cfg.peer} refused to sync: {e}"
