"""Shared test helpers. Run tests from the repo root: python3 -m unittest"""
from __future__ import annotations

import io
import json
import os
import textwrap
import threading
import time
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


class FakePeer:
    """A tiny HTTP server on a random loopback port that answers with canned responses."""

    def __init__(self, respond):
        outer = self
        self.requests: list[tuple[str, str]] = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _answer(self, method: str) -> None:
                outer.requests.append((method, self.path))
                status, body = respond(method, self.path)
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._answer("GET")

            def do_POST(self):
                self._answer("POST")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


FIXTURE_CAPS = REPO / "tests" / "fixtures" / "capabilities"


class Machine:
    """One pretend machine for integration tests: its own data dir, config file and daemon on loopback."""

    def __init__(self, root: Path, me: str, peer: str, port: int, peer_port: int, caps_dir: Path):
        self.dir = root / me
        config.write(self.dir, {"me": me, "peer": peer, "port": port, "bind": "127.0.0.1",
                                "peer_url": f"http://127.0.0.1:{peer_port}", "dev_allow_ips": ["127.0.0.1"],
                                "capabilities_dir": str(caps_dir)})
        self.daemon = None

    def start(self) -> None:
        from orbit import daemon, loader
        self.daemon = daemon.Daemon(loader.open_runtime(config.load(self.dir)))
        self.daemon.start("127.0.0.1")

    def stop(self) -> None:
        if self.daemon:
            self.daemon.close()
            self.daemon = None

    def cli(self, *args: str) -> tuple[int, str, str]:
        return run_cli(self.dir, *args)

    def prompt(self) -> str:
        path = self.dir / "prompt"
        return path.read_text(encoding="utf-8") if path.exists() else ""
