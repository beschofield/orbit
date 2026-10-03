"""Append-only text logs in <data_dir>/logs/<name>.log (one older file kept as .log.1).

Never raises: logging runs inside the login greeting and the daemon, and a full
disk or a missing directory must not break someone's shell.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

MAX_BYTES = 1_000_000  # then <name>.log moves to <name>.log.1, so logs can't fill the disk


def log(data_dir: Path, name: str, message: str) -> None:
    try:
        directory = data_dir / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.log"
        try:
            if path.stat().st_size > MAX_BYTES:
                os.replace(path, directory / f"{name}.log.1")
        except FileNotFoundError:
            pass
        stamp = dt.datetime.now().isoformat(timespec="seconds")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {message}\n")
    except OSError:
        pass
