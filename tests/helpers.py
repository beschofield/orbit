"""Shared test helpers. Run tests from the repo root: python3 -m unittest"""
from __future__ import annotations

import json
import textwrap
import time
from pathlib import Path

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
