"""`orbit update`: pull the latest code and restart orbitd only if the core changed.

Code doesn't sync between the machines (only events do), so after one of you pushes,
the other runs this. It is a core command, not a capability, because it touches the
repo and systemd (invariant 3). It never discards work: a dirty checkout or a diverged
branch is refused with a hint, and nothing is changed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from orbit import characters, config
from orbit.config import Config, ConfigError
from orbit.contract import Say

# A change under any of these means the running orbitd is out of date.
RESTART_PREFIXES = ("orbit/", "bin/", "shell/")
# A change to any of these only takes effect after `install.sh` runs again (it copies the unit file too).
REINSTALL_PATHS = ("shell/orbit.bash", "install.sh", "systemd/orbitd.service")
RESTART_CMD = ["systemctl", "--user", "restart", "orbitd"]


class UpdateError(Exception):
    """Why the update stopped, phrased as "<what> — <how to fix>". Nothing was changed."""


def git(repo: Path, *args: str) -> str:
    """Run git in `repo` and return stdout; raise UpdateError carrying git's own message on failure."""
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise UpdateError("git is not installed — install it (`sudo apt install git`) and try again") from None
    except subprocess.TimeoutExpired:
        raise UpdateError(f"`git {' '.join(args)}` in {repo} took over 2 minutes — check the network "
                          "and that GitHub is reachable, then try again") from None
    if p.returncode != 0:
        raise UpdateError(f"`git {' '.join(args)}` failed in {repo}:\n{p.stderr.strip()}")
    return p.stdout.strip()


def current_commit(repo: Path = config.REPO_ROOT) -> str | None:
    """Short HEAD commit, or None if `repo` isn't a git checkout. orbitd reports it in /health."""
    try:
        return git(repo, "rev-parse", "--short", "HEAD") or None
    except UpdateError:
        return None


def is_ancestor(repo: Path, old: str, new: str) -> bool | None:
    """Is `old` an ancestor of `new`? None when `repo` doesn't have one of the commits (not fetched yet)."""
    try:
        p = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", old, new],
                           capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return {0: True, 1: False}.get(p.returncode)


def pull(repo: Path) -> tuple[str, str]:
    """Fast-forward `repo` from its upstream. Returns (old commit, new commit)."""
    if git(repo, "status", "--porcelain"):
        raise UpdateError(f"you have local changes in {repo} — commit or stash them first "
                          f"(`git -C {repo} status` lists them)")
    old = git(repo, "rev-parse", "HEAD")
    try:
        git(repo, "pull", "--ff-only")
    except UpdateError as e:
        message = str(e).lower()
        if "fast-forward" in message or "diverg" in message:
            raise UpdateError(f"your branch and the remote have diverged in {repo}, so a fast-forward isn't "
                              f"possible — run `git -C {repo} pull --rebase`, sort out any conflicts, "
                              "then `orbit update` again") from None
        raise
    return old, git(repo, "rev-parse", "HEAD")


def needs_restart(changed: list[str]) -> bool:
    return any(path.startswith(RESTART_PREFIXES) for path in changed)


def needs_reinstall(changed: list[str]) -> bool:
    return any(path in REINSTALL_PATHS for path in changed)


def restart_daemon(cfg: Config | None) -> str:
    """Restart orbitd under systemd, or say how to when that isn't possible."""
    if cfg is not None and cfg.dev_allow_ips:
        return "dev mode: restart your `orbit daemon` by hand (systemd runs the real one, not this test setup)"
    if shutil.which("systemctl") is None:
        return f"systemd isn't available here — restart orbitd yourself: `{' '.join(RESTART_CMD)}`"
    p = subprocess.run(RESTART_CMD, capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        return (f"couldn't restart orbitd ({p.stderr.strip() or f'exit {p.returncode}'}) — run "
                f"`{' '.join(RESTART_CMD)}` and check `systemctl --user status orbitd`")
    return "restarted orbitd so it runs the new core"


def wait_for_daemon(cfg: Config, timeout: float = 10.0) -> None:
    """Give a just-restarted orbitd a moment, so the doctor run after it doesn't call it down."""
    from orbit import daemon, sync
    try:
        url = f"http://{daemon.resolve_bind(cfg)}:{cfg.port}/health"
    except daemon.DaemonError:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and sync.get_json(url) is None:
        time.sleep(0.25)


def run_doctor(repo: Path) -> None:
    """Run the *new* code's doctor in a fresh process: this one still has the old modules loaded."""
    subprocess.run([sys.executable, "-m", "orbit.cli", "doctor"], cwd=repo, timeout=60,
                   env={**os.environ, "PYTHONPATH": str(repo)})


def say(who: str, mood: str, text: str) -> None:
    color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    print(characters.render_says([Say(who=who, mood=mood, text=text)], color=color))


def main(args: list[str], repo: Path = config.REPO_ROOT, doctor: bool = True) -> int:
    if args:
        print("usage: orbit update", file=sys.stderr)
        return 2
    try:
        cfg: Config | None = config.load()
    except ConfigError:
        cfg = None  # a broken or missing config shouldn't stop you pulling the fix for it
    who = cfg.me if cfg else "charon"
    try:
        old, new = pull(repo)
        if old == new:
            print(f"already up to date ({new[:7]})")
            say(who, "sleepy", "Nothing new out here. Same orbit as before.")
            return 0
        changed = git(repo, "diff", "--name-only", old, new).splitlines()
        log = git(repo, "log", "--oneline", f"{old}..{new}")
    except UpdateError as e:
        print(f"orbit update: {e}", file=sys.stderr)
        return 1

    print(f"updated {old[:7]} → {new[:7]}:\n{log}\n")
    restarted = needs_restart(changed)
    if restarted:
        print(restart_daemon(cfg))
    elif any(path.startswith("capabilities/") for path in changed):
        print("only capabilities changed — no restart needed; orbitd picks them up within 30 s")
    else:
        print("no running code changed — no restart needed")
    if needs_reinstall(changed):
        print(f"the shell snippet or installer changed — run `{repo}/install.sh` again "
              "(it's safe to re-run; it replaces the bashrc block)")

    if cfg is None:
        print("\nno config yet, so skipping `orbit doctor` — run `orbit init` first")
    elif doctor:
        if restarted and not cfg.dev_allow_ips:
            wait_for_daemon(cfg)
        print()
        sys.stdout.flush()  # the doctor subprocess writes straight to the same terminal
        run_doctor(repo)
    say(who, "love", "Fresh code, same orbit ♥" if who == "charon" else "New code, same us ♥")
    return 0
