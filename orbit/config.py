"""Loads ~/.orbit/config.json ($ORBIT_DIR overrides ~/.orbit). Every error says how to fix it."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

CHARACTERS = ("pluto", "charon")
DEFAULT_PORT = 1978   # the year Charon was discovered
DEV_PEER_PORT = 1979  # where `orbit dev peer` listens
REPO_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(Exception):
    """A config problem, phrased as "<where>: <what's wrong> — <how to fix>"."""


@dataclass(frozen=True)
class Config:
    me: str
    peer: str
    peer_host: str
    port: int
    capabilities_dir: Path
    prompt_order: list[str]
    data_dir: Path
    peer_url: str
    bind: str | None          # None = this machine's tailnet IP (`tailscale ip -4`)
    dev_allow_ips: list[str]  # non-empty = dev/test mode: trust these IPs instead of `tailscale whois`

    @property
    def db_path(self) -> Path:
        return self.data_dir / "orbit.db"

    @property
    def prompt_path(self) -> Path:
        return self.data_dir / "prompt"


def data_dir() -> Path:
    env = os.environ.get("ORBIT_DIR")
    return Path(env) if env else Path.home() / ".orbit"


def load(directory: Path | None = None) -> Config:
    directory = directory or data_dir()
    path = directory / "config.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"{path}: not found — run `orbit init --me charon --peer pluto` "
                          "(the other way round on pluto)") from None
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path}: invalid JSON at line {e.lineno}, column {e.colno} — fix the syntax") from None
    return from_dict(raw, directory, str(path))


_KIND_NAMES = {int: "a whole number", str: "a string", list: "a list"}


def from_dict(raw: object, directory: Path, source: str) -> Config:
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: must be a JSON object")

    def get(key: str, kind: type, default):
        value = raw.get(key, default)
        if not isinstance(value, kind) or isinstance(value, bool):
            raise ConfigError(f'{source}: "{key}" must be {_KIND_NAMES[kind]} — got {json.dumps(value)}')
        return value

    for key in ("me", "peer"):
        if key not in raw:
            raise ConfigError(f'{source}: missing "{key}" — add "{key}": "pluto" or "charon"')
        if raw[key] not in CHARACTERS:
            raise ConfigError(f'{source}: "{key}" must be "pluto" or "charon" — got {json.dumps(raw[key])}')
    me, peer = raw["me"], raw["peer"]
    if me == peer:
        raise ConfigError(f'{source}: "me" and "peer" are both "{me}" — they must be different machines')

    port = get("port", int, DEFAULT_PORT)
    peer_host = get("peer_host", str, peer)
    bind = raw.get("bind")
    if bind is not None and not isinstance(bind, str):
        raise ConfigError(f'{source}: "bind" must be a string IP address or left out')
    return Config(
        me=me,
        peer=peer,
        peer_host=peer_host,
        port=port,
        capabilities_dir=Path(get("capabilities_dir", str, str(REPO_ROOT / "capabilities"))).expanduser(),
        prompt_order=[str(x) for x in get("prompt_order", list, ["presence", "notes"])],
        data_dir=directory,
        peer_url=get("peer_url", str, f"http://{peer_host}:{port}").rstrip("/"),
        bind=bind,
        dev_allow_ips=[str(x) for x in get("dev_allow_ips", list, [])],
    )


def write(directory: Path, values: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "config.json"
    path.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    return path
