"""Finds capabilities, runs them as subprocesses, and applies what they return.

Capabilities never touch the DB: everything they need arrives on stdin (build_input),
and every change comes back as an Output (apply). `execute` is pure, which is what
`orbit dev` uses. `run` adds the bookkeeping: logs, failure counts, auto-disable.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from orbit import prompt
from orbit.config import Config
from orbit.contract import ContractError, Manifest, Output, parse_manifest, parse_output
from orbit.log import log
from orbit.store import Event, Store, now_iso

TIMEOUTS = {"command": 10.0, "login": 0.8, "tick": 2.0, "received": 2.0}
MAX_FAILURES = 5
RECENT_LIMIT = 200


@dataclass
class Runtime:
    cfg: Config
    store: Store
    manifests: dict[str, Manifest]
    problems: list[str] = field(default_factory=list)

    def commands(self) -> dict[str, Manifest]:
        """Command name -> owning capability. Duplicated names are left out (discover reports them)."""
        owners: dict[str, list[Manifest]] = {}
        for m in self.manifests.values():
            for c in m.commands:
                owners.setdefault(c.name, []).append(m)
        return {name: ms[0] for name, ms in owners.items() if len(ms) == 1}


@dataclass(frozen=True)
class RunResult:
    output: Output | None
    error: str | None = None
    stderr: str = ""
    timed_out: bool = False


def open_runtime(cfg: Config) -> Runtime:
    manifests, problems = discover(cfg.capabilities_dir)
    return Runtime(cfg, Store(cfg.db_path, cfg.me), manifests, problems)


def discover(cap_dir: Path) -> tuple[dict[str, Manifest], list[str]]:
    if not cap_dir.is_dir():
        return {}, [f"{cap_dir}: capabilities folder not found — set capabilities_dir in config.json"]
    manifests: dict[str, Manifest] = {}
    problems: list[str] = []
    for d in sorted(p for p in cap_dir.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        try:
            manifests[d.name] = parse_manifest(d / "manifest.json")
        except ContractError as e:
            problems.extend(e.problems)
        except Exception as e:  # e.g. a manifest that isn't UTF-8: one bad folder mustn't hide the rest
            problems.append(f"{d}/manifest.json: could not read ({type(e).__name__}: {e}) — fix the file")
    owners: dict[str, list[str]] = {}
    for m in manifests.values():
        for c in m.commands:
            owners.setdefault(c.name, []).append(m.name)
    for cmd, names in sorted(owners.items()):
        if len(names) > 1:
            problems.append(f"command {cmd!r} is declared by {', '.join(names)} — "
                            "rename it in one of them; neither gets it until then")
    return manifests, problems


def folder_signature(cap_dir: Path) -> dict[str, int]:
    """Capability folder name -> newest mtime of its top-level files.

    Cheap enough to run every 30 s, and it changes when a capability is added, removed,
    or has its manifest or program edited, which is when orbitd must re-discover.
    """
    sig: dict[str, int] = {}
    try:
        dirs = [p for p in cap_dir.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))]
    except OSError:
        return sig
    for d in dirs:
        try:
            sig[d.name] = max([d.stat().st_mtime_ns, *(p.stat().st_mtime_ns for p in d.iterdir() if p.is_file())])
        except OSError:
            sig[d.name] = -1
    return sig


def build_input(rt: Runtime, m: Manifest, trigger: dict) -> dict:
    latest: dict[str, dict] = {rt.cfg.me: {}, rt.cfg.peer: {}}
    for origin, by_type in rt.store.latest_all().items():
        latest.setdefault(origin, {}).update({t: e.to_dict() for t, e in by_type.items()})
    return {
        "contract": 1,
        "trigger": trigger,
        "me": {"name": rt.cfg.me},
        "peer": {"name": rt.cfg.peer, **rt.store.peer_status()},
        "now": now_iso(),
        "events": [e.to_dict() for e in rt.store.recent(list(m.event_types), RECENT_LIMIT)],
        "latest": latest,
    }


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value or ""


def execute(m: Manifest, payload: dict, timeout: float, env: dict | None = None) -> RunResult:
    try:
        proc = subprocess.run([str(m.run)], input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                              encoding="utf-8", errors="replace", timeout=timeout, cwd=m.dir, env=env)
    except subprocess.TimeoutExpired as e:
        return RunResult(None, f"{m.name}: timed out after {timeout:g}s — make it faster "
                               "(slow work belongs in a tick, which has its own timeout)", _text(e.stderr), True)
    except OSError as e:
        return RunResult(None, f"{m.name}: could not start {m.run}: {e} — check the shebang line and chmod +x")
    if proc.returncode != 0:
        return RunResult(None, f"{m.name}: exited with code {proc.returncode} — see its stderr", proc.stderr)
    try:
        return RunResult(parse_output(proc.stdout, m), None, proc.stderr)
    except ContractError as e:
        return RunResult(None, "\n".join(e.problems), proc.stderr)


def run(rt: Runtime, m: Manifest, trigger: dict) -> RunResult:
    kind = trigger["kind"]
    if is_disabled(rt, m):
        return RunResult(None, f"{m.name} is disabled after {MAX_FAILURES} failures in a row — "
                               f"fix it, then run `orbit doctor --reset {m.name}`")
    res = execute(m, build_input(rt, m, trigger), TIMEOUTS[kind])
    if res.stderr.strip():
        log(rt.cfg.data_dir, m.name, f"stderr ({kind}): {res.stderr.strip()}")
    if res.output is None:
        log(rt.cfg.data_dir, m.name, f"FAILED ({kind}): {res.error}")
        if kind == "login" and res.timed_out:
            # 0.8 s is tight and a busy machine can miss it; that isn't the capability's fault.
            log(rt.cfg.data_dir, m.name, "(login timeouts don't count toward disabling)")
        else:
            _record_failure(rt, m)
    else:
        rt.store.delete_meta(f"fail:{m.name}")
    return res


def apply(rt: Runtime, m: Manifest, out: Output, kind: str) -> list[Event]:
    emitted = [rt.store.append(e.type, e.data, keep=m.event_types[e.type], v=e.v) for e in out.emit]
    if out.prompt is not None:
        prompt.set_segment(rt.store, m.name, out.prompt)
        prompt.rebuild(rt.store, rt.cfg, rt.manifests)
    if out.say and kind in ("tick", "received"):
        log(rt.cfg.data_dir, m.name, f"say is ignored for {kind} triggers (no terminal) — use prompt instead")
    return emitted


def invoke(rt: Runtime, m: Manifest, trigger: dict) -> RunResult:
    res = run(rt, m, trigger)
    if res.output is not None:
        apply(rt, m, res.output, trigger["kind"])
    return res


def signature(m: Manifest) -> str:
    """Newest mtime of any file in the capability; editing anything re-enables it."""
    files = (p for p in m.dir.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    return str(max((p.stat().st_mtime_ns for p in files), default=0))


def is_disabled(rt: Runtime, m: Manifest) -> bool:
    sig = rt.store.get_meta(f"disabled:{m.name}")
    if sig is None:
        return False
    if sig != signature(m):
        reset(rt, m.name)
        return False
    return True


def reset(rt: Runtime, name: str) -> None:
    rt.store.delete_meta(f"fail:{name}")
    rt.store.delete_meta(f"disabled:{name}")


def _record_failure(rt: Runtime, m: Manifest) -> None:
    count = int(rt.store.get_meta(f"fail:{m.name}") or 0) + 1
    rt.store.set_meta(f"fail:{m.name}", str(count))
    if count >= MAX_FAILURES:
        rt.store.set_meta(f"disabled:{m.name}", signature(m))
        log(rt.cfg.data_dir, m.name, f"DISABLED after {count} failures in a row — fix it, then run "
                                     f"`orbit doctor --reset {m.name}` (or edit any file in its folder)")
