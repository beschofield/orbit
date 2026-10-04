"""Tailnet names and addresses, so the peer is always reached over Tailscale.

A bare name like "charon" can resolve to the peer's LAN address when both machines
share a network (systemd-resolved answers it over LLMNR before MagicDNS). orbitd only
listens on the tailnet IP, so that address refuses the connection, and only some of
the time, depending on which answer wins. The MagicDNS name (charon.<tailnet>.ts.net)
always resolves to the tailnet IP.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import subprocess

# Tailscale hands out addresses from these ranges (CGNAT IPv4 and its ULA IPv6 prefix).
TAILNET_NETS = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))


def magicdns_suffix() -> str | None:
    """The tailnet's MagicDNS suffix, e.g. "tail1234.ts.net", or None if MagicDNS is off or Tailscale is down."""
    try:
        out = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=5)
        status = json.loads(out.stdout) if out.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    if not isinstance(status, dict) or not (status.get("CurrentTailnet") or {}).get("MagicDNSEnabled"):
        return None
    return (status.get("MagicDNSSuffix") or "").strip(".") or None


def is_tailnet_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])  # drop an IPv6 zone like fe80::1%eth0
    except ValueError:
        return False
    return any(ip in net for net in TAILNET_NETS)


def off_tailnet_addresses(host: str) -> list[str]:
    """Addresses `host` resolves to that aren't on the tailnet. Empty if all are, or it doesn't resolve.

    An IP literal is left alone: whoever typed it into config.json chose it on purpose.
    """
    try:
        ipaddress.ip_address(host)
        return []
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        return []  # not resolving at all is reported by the "not answering" check
    found = dict.fromkeys(str(info[4][0]) for info in infos)  # keeps order, drops duplicates
    return [a for a in found if not is_tailnet_ip(a)]
