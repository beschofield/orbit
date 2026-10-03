import json
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from orbit import daemon, loader
from tests.helpers import FIXTURE_CAPS, Machine, make_cfg, wait_for


class AuthorizerTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def whois(self, ip):
        self.calls.append(ip)
        return {"100.1.1.1": "pluto", "100.2.2.2": "charon"}.get(ip)

    def test_whois_match_and_cache(self):
        auth = daemon.Authorizer(make_cfg(Path("/tmp")), whois=self.whois)
        self.assertTrue(auth.allowed("100.1.1.1"))
        self.assertTrue(auth.allowed("100.1.1.1"))
        self.assertFalse(auth.allowed("100.2.2.2"))
        self.assertEqual(self.calls, ["100.1.1.1", "100.2.2.2"])

    def test_fqdn_peer_host_matches_short_name(self):
        auth = daemon.Authorizer(make_cfg(Path("/tmp"), peer_host="pluto.tail123.ts.net"), whois=self.whois)
        self.assertTrue(auth.allowed("100.1.1.1"))

    def test_dev_allowlist_skips_whois(self):
        auth = daemon.Authorizer(make_cfg(Path("/tmp"), dev_allow_ips=["127.0.0.1"]), whois=self.whois)
        self.assertTrue(auth.allowed("127.0.0.1"))
        self.assertFalse(auth.allowed("100.1.1.1"))
        self.assertEqual(self.calls, [])


class ResolveBindTest(unittest.TestCase):
    def test_explicit_bind(self):
        self.assertEqual(daemon.resolve_bind(make_cfg(Path("/tmp"), bind="127.0.0.1")), "127.0.0.1")

    def test_tailscale_down_message(self):
        done = subprocess.CompletedProcess(["tailscale"], 1, "", "not running")
        with mock.patch("subprocess.run", return_value=done), self.assertRaises(daemon.DaemonError) as ctx:
            daemon.resolve_bind(make_cfg(Path("/tmp")))
        self.assertIn("tailscale status", str(ctx.exception))

    def test_tailscale_missing_message(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("tailscale")), \
                self.assertRaises(daemon.DaemonError) as ctx:
            daemon.resolve_bind(make_cfg(Path("/tmp")))
        self.assertIn("Tailscale installed", str(ctx.exception))


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None


def post(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=b"", method="POST"), timeout=3) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


class HttpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.daemons = []

    def tearDown(self):
        for d in self.daemons:
            d.close()
        self.tmp.cleanup()

    def start(self, allow):
        cfg = make_cfg(Path(self.tmp.name) / str(len(self.daemons)), caps_dir=FIXTURE_CAPS, port=19782,
                       bind="127.0.0.1", peer_url="http://127.0.0.1:9", dev_allow_ips=allow)
        d = daemon.Daemon(loader.open_runtime(cfg))
        d.start("127.0.0.1")
        self.daemons.append(d)
        return d

    def test_health_is_open_but_events_and_poke_need_auth(self):
        self.start(["10.0.0.1"])  # loopback is NOT allowed
        status, body = get("http://127.0.0.1:19782/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["me"], "charon")
        self.assertEqual(body["capabilities"], ["ping"])
        self.assertRegex(body["instance"], r"^[0-9a-f]{32}$")
        self.assertEqual(get("http://127.0.0.1:19782/events?after=0")[0], 403)
        self.assertEqual(post("http://127.0.0.1:19782/poke"), 403)

    def test_events_paging_bad_params_poke_and_404(self):
        d = self.start(["127.0.0.1"])
        for _ in range(3):
            d.rt.store.append("ping.sent", {})
        status, body = get("http://127.0.0.1:19782/events?after=0&limit=2")
        self.assertEqual(status, 200)
        self.assertEqual([e["seq"] for e in body["events"]], [1, 2])
        self.assertTrue(body["has_more"])
        self.assertEqual(body["events"][0]["keep"], "log")
        self.assertEqual(body["instance"], d.rt.store.instance())
        self.assertEqual(get("http://127.0.0.1:19782/events?after=x")[0], 400)
        self.assertEqual(post("http://127.0.0.1:19782/poke"), 204)
        self.assertEqual(get("http://127.0.0.1:19782/nope")[0], 404)


class TwoMachineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.charon = Machine(root, "charon", "pluto", 19780, 19781, FIXTURE_CAPS)
        self.pluto = Machine(root, "pluto", "charon", 19781, 19780, FIXTURE_CAPS)
        self.charon.start()
        self.pluto.start()

    def tearDown(self):
        self.charon.stop()
        self.pluto.stop()
        self.tmp.cleanup()

    def test_command_on_one_machine_reaches_the_other(self):
        self.assertEqual(self.charon.cli("ping")[0], 0)
        self.assertTrue(wait_for(lambda: self.pluto.prompt() == "got 1"), self.pluto.prompt())

    def test_offline_peer_catches_up_on_restart(self):
        self.charon.cli("ping")
        self.assertTrue(wait_for(lambda: self.pluto.prompt() == "got 1"))
        self.pluto.stop()
        self.charon.cli("ping")
        self.charon.cli("ping")
        self.pluto.start()
        self.assertTrue(wait_for(lambda: self.pluto.prompt() == "got 3"), self.pluto.prompt())

    def test_loop_survives_exceptions(self):
        with mock.patch("orbit.sync.pull_once", side_effect=RuntimeError("boom")):
            self.charon.daemon.poke.set()
            time.sleep(1)
            self.assertTrue(self.charon.daemon.loop_thread.is_alive())
        log = (self.charon.dir / "logs" / "orbitd.log").read_text(encoding="utf-8")
        self.assertIn("RuntimeError: boom", log)
