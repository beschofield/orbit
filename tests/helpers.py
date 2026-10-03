"""Shared test helpers. Run tests from the repo root: python3 -m unittest"""
from __future__ import annotations

import io
import json
import os
import textwrap
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from orbit import config

REPO = Path(__file__).resolve().parent.parent


def make_cfg(data_dir: Path, me: str = "charon", peer: str = "pluto",
             caps_dir: Path | None = None, **extra) -> config.Config:
    """A Config for tests, without writing a file. `extra` overrides any config key."""
    raw = {"me": me, "peer": peer, "capabilities_dir": str(caps_dir or REPO / "capabilities"), **extra}
    return config.from_dict(raw, data_dir, "test config")


def wait_for(condition, timeout: float = 5.0, interval: float = 0.05) -> bool:
    """Poll `condition()` until it's truthy or `timeout` passes. Returns the last result."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return bool(condition())


def write_cap(root: Path, folder: str, script: str, **manifest) -> Path:
    """Create <root>/<folder>/ with manifest.json (keys overridable via kwargs) and an executable main.py."""
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    data = {"name": folder, "description": f"test capability {folder}", "contract": 1, "run": "main.py",
            "commands": [], "triggers": [], "tick_seconds": None, "event_types": {}, "receives": []}
    data.update(manifest)
    (d / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    run = d / "main.py"
    run.write_text(script, encoding="utf-8")
    run.chmod(0o755)
    return d


def py(body: str) -> str:
    """A Python capability script. `inp` is the parsed stdin; `body` prints the output."""
    return ("#!/usr/bin/env python3\nimport json, os, sys, time\ninp = json.load(sys.stdin)\n"
            + textwrap.dedent(body).strip() + "\n")


def make_runtime(data_dir: Path, caps_dir: Path, **extra):
    """A loader.Runtime over a temporary data dir and capabilities folder."""
    from orbit import loader
    return loader.open_runtime(make_cfg(data_dir, caps_dir=caps_dir, **extra))


def run_cli(data_dir: Path, *args: str) -> tuple[int, str, str]:
    """Run `orbit <args>` in-process against data_dir. Returns (exit code, stdout, stderr)."""
    from orbit import cli
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, {"ORBIT_DIR": str(data_dir), "NO_COLOR": "1"}), \
            redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(args))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue(), err.getvalue()
