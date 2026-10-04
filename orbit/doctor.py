"""`orbit doctor`: one command that says what works, what doesn't, and how to fix it."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

from urllib.parse import urlsplit

from orbit import CORE_VERSION, config, daemon, loader, sync, tailnet, update


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
            started, on_disk_commit = mine.get("commit"), update.current_commit()
            if started and on_disk_commit and started != on_disk_commit \
                    and update.core_changed_since(config.REPO_ROOT, started):
                yield False, (f"orbitd is still running {started}, but the checkout is on {on_disk_commit} with "
                              "core changes — `systemctl --user restart orbitd`")
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

    yield from peer_address_check(cfg)
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
                      f"{theirs.get('core_version')} — run `orbit update` on both machines")
    behind = commit_mismatch(cfg.me, cfg.peer, update.current_commit(), theirs.get("commit"))
    if behind:
        yield False, behind
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


def peer_address_check(cfg: config.Config) -> Iterator[tuple[bool, str]]:
    """Flag a peer name that resolves off the tailnet: orbitd there refuses it, but only some of the time."""
    if cfg.dev_allow_ips:
        return  # dev/test setups talk over loopback on purpose
    host = urlsplit(cfg.peer_url).hostname or ""
    off = tailnet.off_tailnet_addresses(host)
    if not off:
        return
    suffix = tailnet.magicdns_suffix()
    fix = (f'set "peer_host": "{cfg.peer}.{suffix}"' if suffix
           else f"set peer_host to {cfg.peer}'s MagicDNS name or tailnet IP (`tailscale ip -4 {cfg.peer}`)")
    yield False, (f"{host} resolves to {', '.join(off)}, which isn't a tailnet address, so syncing can fail "
                  f"on and off — {fix} in {cfg.data_dir}/config.json, then `systemctl --user restart orbitd`")


def commit_mismatch(me: str, peer: str, mine: str | None, theirs: str | None,
                    repo: Path = config.REPO_ROOT) -> str | None:
    """Say which machine needs `orbit update`, or None if both run the same commit.

    The older machine is the one whose commit is an ancestor of the other's. If this
    checkout doesn't have the peer's commit, it's either pushed and not pulled here yet,
    or never pushed from the peer, and only the peer can tell which.
    """
    if not mine or not theirs or mine == theirs:
        return None  # same code, or one side isn't a git checkout
    where = f"{peer} is on {theirs}, {me} is on {mine}"
    peer_older = update.is_ancestor(repo, theirs, mine)
    if peer_older:
        return f"{where} — run `orbit update` on {peer}"
    if peer_older is None:
        return (f"{where}, which this checkout doesn't have — run `orbit update` on {me}; if that doesn't "
                f"fetch it, {peer} has unpushed commits: push them from {peer} first")
    if update.is_ancestor(repo, mine, theirs):
        return f"{where} — run `orbit update` on {me}"
    return f"{where} — the two checkouts have diverged; push from one, then `orbit update` on the other"
