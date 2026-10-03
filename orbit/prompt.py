"""Builds ~/.orbit/prompt, the one file the shell reads on every prompt.

The shell only ever does $(<file), so Python never runs on the prompt path. Each
capability owns one segment (stored in meta as prompt:<name>). Whoever ran the
capability, the CLI or the daemon, rebuilds the file right away.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Iterable

from orbit.config import Config
from orbit.store import Store

SEPARATOR = " · "


def set_segment(store: Store, name: str, text: str) -> None:
    key = f"prompt:{name}"
    if text:
        store.set_meta(key, text)
    else:
        store.delete_meta(key)


def build(store: Store, order: list[str], names: Iterable[str]) -> str:
    segments = {n: store.get_meta(f"prompt:{n}") for n in names}
    ordered = [n for n in order if n in segments] + sorted(n for n in segments if n not in order)
    return SEPARATOR.join(segments[n] for n in ordered if segments[n])


def write_atomic(path: Path, text: str) -> None:
    """Write via a temp file and rename, so the shell never reads a half-written prompt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def rebuild(store: Store, cfg: Config, names: Iterable[str]) -> str:
    text = build(store, cfg.prompt_order, names)
    write_atomic(cfg.prompt_path, text)
    return text
