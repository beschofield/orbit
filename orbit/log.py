"""Append-only text logs in <data_dir>/logs/<name>.log.

Never raises: logging runs inside the login greeting and the daemon, and a full
disk or a missing directory must not break someone's shell.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path


def log(data_dir: Path, name: str, message: str) -> None:
    try:
        directory = data_dir / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().isoformat(timespec="seconds")
        with open(directory / f"{name}.log", "a", encoding="utf-8") as f:
            f.write(f"{stamp} {message}\n")
    except OSError:
        pass
