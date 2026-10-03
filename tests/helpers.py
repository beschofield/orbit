"""Shared test helpers. Run tests from the repo root: python3 -m unittest"""
from __future__ import annotations

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
