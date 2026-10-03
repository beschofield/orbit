"""orbitd: serves this machine's events to the peer, pulls the peer's, runs ticks.

HTTP listens only on this machine's tailnet IP (or `bind`). Every request except
/health must come from the configured peer, checked with `tailscale whois`; in dev/test
mode a static IP allowlist replaces that check. The main loop catches every exception
and keeps going: a broken capability or a flaky peer must never stop the daemon.
"""
from __future__ import annotations

import json
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from orbit import CORE_VERSION, loader, prompt, sync
from orbit.config import Config
from orbit.log import log

WHOIS_TTL = 300.0
RESCAN_SECONDS = 30.0  # how often orbitd looks for new or changed capabilities


class DaemonError(Exception):
    pass


def resolve_bind(cfg: Config) -> str:
    if cfg.bind:
        return cfg.bind
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise DaemonError(f"could not run `tailscale ip -4` ({e}) — is Tailscale installed?") from None
    lines = out.stdout.strip().splitlines() if out.returncode == 0 else []
    if not lines:
        raise DaemonError("`tailscale ip -4` gave no address — is Tailscale up and logged in? "
                          "Check with `tailscale status`")
    return lines[0].strip()


def whois_name(ip: str) -> str | None:
    """The tailnet machine name for an IP, e.g. "pluto", or None if unknown."""
    try:
        out = subprocess.run(["tailscale", "whois", "--json", ip], capture_output=True, text=True, timeout=5)
        node = json.loads(out.stdout).get("Node", {}) if out.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, AttributeError):
        return None
    name = node.get("ComputedName") or (node.get("Name") or "").split(".")[0]
    return name or None


class Authorizer:
    def __init__(self, cfg: Config, whois=whois_name, clock=time.monotonic):
        self.cfg, self.whois, self.clock = cfg, whois, clock
        self.expected = cfg.peer_host.split(".")[0]
        self.cache: dict[str, tuple[float, str | None]] = {}
        self.lock = threading.Lock()

    def allowed(self, ip: str) -> bool:
        if self.cfg.dev_allow_ips:
            return ip in self.cfg.dev_allow_ips
        with self.lock:
            hit = self.cache.get(ip)
        if hit and self.clock() - hit[0] < WHOIS_TTL:
            name = hit[1]
        else:
            name = self.whois(ip)
            with self.lock:
                self.cache[ip] = (self.clock(), name)
        return name == self.expected


def health(rt: loader.Runtime) -> dict:
    return {"ok": True, "me": rt.cfg.me, "core_version": CORE_VERSION, "capabilities": sorted(rt.manifests),
            "instance": rt.store.instance()}


def make_handler(rt: loader.Runtime, auth: Authorizer, poke: threading.Event):
    class Handler(BaseHTTPRequestHandler):
        server_version = "orbitd"

        def log_message(self, fmt, *args):  # quiet: problems go to orbitd.log
            pass

        def _send(self, code: int, body: dict | None = None) -> None:
            data = b"" if body is None else json.dumps(body).encode()
            self.send_response(code)
            if body is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            try:
                url = urllib.parse.urlsplit(self.path)
                if url.path == "/health":
                    return self._send(200, health(rt))
                if not auth.allowed(self.client_address[0]):
                    return self._send(403, {"error": "not the configured peer"})
                if url.path != "/events":
                    return self._send(404, {"error": "not found"})
                query = urllib.parse.parse_qs(url.query)
                try:
                    after = int(query.get("after", ["0"])[0])
                    limit = max(1, min(int(query.get("limit", [str(sync.PAGE)])[0]), sync.PAGE))
                except ValueError:
                    return self._send(400, {"error": "after and limit must be whole numbers"})
                rows = rt.store.own_after(after, limit + 1)
                self._send(200, {"events": [{**e.to_dict(), "keep": keep} for e, keep in rows[:limit]],
                                 "has_more": len(rows) > limit, "core_version": CORE_VERSION,
                                 "capabilities": sorted(rt.manifests), "instance": rt.store.instance()})
            finally:
                rt.store.release()

        def do_POST(self):
            try:
                path = urllib.parse.urlsplit(self.path).path
                if not auth.allowed(self.client_address[0]):
                    return self._send(403, {"error": "not the configured peer"})
                if path != "/poke":
                    return self._send(404, {"error": "not found"})
                poke.set()
                self._send(204)
            finally:
                rt.store.release()

    return Handler


class Daemon:
    def __init__(self, rt: loader.Runtime, whois=whois_name):
        self.rt = rt
        self.stop = threading.Event()
        self.poke = threading.Event()
        self.auth = Authorizer(rt.cfg, whois)
        self.server: ThreadingHTTPServer | None = None
        self.loop_thread: threading.Thread | None = None
        self.caps_signature: dict[str, int] = {}

    def start(self, host: str) -> None:
        self.server = ThreadingHTTPServer((host, self.rt.cfg.port), make_handler(self.rt, self.auth, self.poke))
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True, name="orbitd-http").start()
        self.loop_thread = threading.Thread(target=self.loop, daemon=True, name="orbitd-loop")
        self.loop_thread.start()

    def _safely(self, what: str, fn):
        try:
            return fn()
        except Exception as e:
            log(self.rt.cfg.data_dir, "orbitd", f"{what} crashed: {type(e).__name__}: {e}")
            return None

    def rescan(self, ticks: dict[str, float]) -> None:
        """Re-discover capabilities if their folder changed, so adding one needs no restart.

        The Runtime's attributes are replaced (not mutated) because HTTP threads read them.
        `ticks` keeps existing schedules; new tick capabilities are due at once.
        """
        rt = self.rt
        sig = loader.folder_signature(rt.cfg.capabilities_dir)
        if sig == self.caps_signature:
            return
        self.caps_signature = sig
        manifests, problems = loader.discover(rt.cfg.capabilities_dir)
        old = set(rt.manifests)
        added, removed = sorted(set(manifests) - old), sorted(old - set(manifests))
        rt.manifests, rt.problems = manifests, problems
        parts = [f"added {', '.join(added)}" if added else "", f"removed {', '.join(removed)}" if removed else ""]
        log(rt.cfg.data_dir, "orbitd", f"capabilities changed: {'; '.join(p for p in parts if p) or 'edited'}"
                                       f" (now: {', '.join(sorted(manifests)) or 'none'})")
        for p in problems:
            log(rt.cfg.data_dir, "orbitd", f"capability problem: {p}")
        for name in list(ticks):
            if name not in manifests or "tick" not in manifests[name].triggers:
                del ticks[name]
        for name, m in manifests.items():
            if "tick" in m.triggers:
                ticks.setdefault(name, 0.0)
        prompt.rebuild(rt.store, rt.cfg, rt.manifests)

    def loop(self) -> None:
        rt = self.rt
        self._safely("prompt rebuild", lambda: prompt.rebuild(rt.store, rt.cfg, rt.manifests))
        backoff = sync.Backoff()
        next_pull = 0.0
        ticks = {name: 0.0 for name, m in rt.manifests.items() if "tick" in m.triggers}
        self.caps_signature = loader.folder_signature(rt.cfg.capabilities_dir)
        next_rescan = time.monotonic() + RESCAN_SECONDS
        while not self.stop.is_set():
            now = time.monotonic()
            if now >= next_rescan:
                self._safely("capability rescan", lambda: self.rescan(ticks))
                next_rescan = now + RESCAN_SECONDS
            if self.poke.is_set() or now >= next_pull:
                self.poke.clear()
                ok = self._safely("pull", lambda: sync.pull_once(rt))
                if ok:
                    backoff.reset()
                    next_pull = now + sync.PULL_INTERVAL
                else:
                    next_pull = now + backoff.next()
            for name, due in list(ticks.items()):
                m = rt.manifests.get(name)
                if m is None:  # removed by a rescan
                    del ticks[name]
                    continue
                if now >= due:
                    res = self._safely(f"{name} tick", lambda m=m: loader.invoke(rt, m, {"kind": "tick"}))
                    if res and res.output and res.output.emit:
                        sync.poke_peer(rt.cfg)
                    ticks[name] = now + m.tick_seconds
            self.poke.wait(timeout=0.5)

    def close(self) -> None:
        self.stop.set()
        self.poke.set()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.loop_thread:
            self.loop_thread.join(timeout=5)
        self.rt.store.close()


def main(cfg: Config) -> int:
    rt = loader.open_runtime(cfg)
    for p in rt.problems:
        log(cfg.data_dir, "orbitd", f"capability problem: {p}")
    while True:
        try:
            host = resolve_bind(cfg)
            break
        except DaemonError as e:  # Tailscale may still be starting at boot
            log(cfg.data_dir, "orbitd", f"{e} (retrying in 10 s)")
            print(f"orbitd: {e} (retrying in 10 s)", file=sys.stderr)
            time.sleep(10)
    d = Daemon(rt)
    try:
        d.start(host)
    except OSError as e:
        print(f"orbitd: cannot listen on {host}:{cfg.port}: {e} — is another orbitd running? "
              "(`systemctl --user status orbitd`)", file=sys.stderr)
        rt.store.close()
        return 1
    log(cfg.data_dir, "orbitd", f"listening on {host}:{cfg.port} as {cfg.me}; peer {cfg.peer_url}")
    signal.signal(signal.SIGTERM, lambda *_: d.stop.set())
    try:
        while not d.stop.wait(1.0):
            pass
    except KeyboardInterrupt:
        pass
    d.close()
    return 0
