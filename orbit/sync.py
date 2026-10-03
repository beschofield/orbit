"""Peer sync. (Task 7 fills in the rest; poke_peer is needed by the CLI first.)"""
from __future__ import annotations

import urllib.request

from orbit.config import Config


def poke_peer(cfg: Config, timeout: float = 1.0) -> bool:
    """Tell the peer we have new events. Failures are fine: its 30 s pull catches up."""
    try:
        req = urllib.request.Request(f"{cfg.peer_url}/poke", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False
