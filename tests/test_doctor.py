import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orbit import config, devtools, loader
from tests.helpers import FIXTURE_CAPS, Machine, py, run_cli, write_cap


class DoctorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def lonely(self, caps: Path) -> Path:
        data = self.root / "lonely"
        config.write(data, {"me": "charon", "peer": "pluto", "port": 19783, "bind": "127.0.0.1",
                            "peer_url": "http://127.0.0.1:9", "capabilities_dir": str(caps)})
        return data

    def test_reports_problems_and_nothing_running(self):
        caps = self.root / "caps"
        write_cap(caps, "good", py('print("{}")'))
        write_cap(caps, "bad", py('print("{}")'), contract=2)
        code, out, _ = run_cli(self.lonely(caps), "doctor")
        self.assertEqual(code, 1)
        self.assertIn("✗", out)
        self.assertIn("contract: must be 1", out)
        self.assertIn("orbitd is not answering on 127.0.0.1:19783", out)
        self.assertIn("pluto is not answering", out)

    def test_reports_and_resets_a_disabled_capability(self):
        caps = self.root / "caps"
        write_cap(caps, "boom", py("sys.exit(1)"))
        data = self.lonely(caps)
        rt = loader.open_runtime(config.load(data))
        for _ in range(5):
            loader.run(rt, rt.manifests["boom"], {"kind": "tick"})
        rt.store.close()
        self.assertIn("boom is disabled", run_cli(data, "doctor")[1])
        self.assertEqual(run_cli(data, "doctor", "--reset", "boom")[0], 0)
        self.assertNotIn("boom is disabled", run_cli(data, "doctor")[1])

    def test_all_good_with_both_daemons_running(self):
        charon = Machine(self.root, "charon", "pluto", 19780, 19781, FIXTURE_CAPS)
        pluto = Machine(self.root, "pluto", "charon", 19781, 19780, FIXTURE_CAPS)
        charon.start()
        pluto.start()
        try:
            code, out, _ = charon.cli("doctor")
            self.assertEqual(code, 0, out)
            self.assertIn("pluto accepts requests from charon", out)
        finally:
            charon.stop()
            pluto.stop()

    def test_running_daemon_with_old_capabilities_is_flagged(self):
        caps = self.root / "caps"
        write_cap(caps, "ping", py('print("{}")'))
        charon = Machine(self.root, "charon", "pluto", 19780, 19781, caps)
        charon.start()
        try:
            write_cap(caps, "fresh", py('print("{}")'))
            out = charon.cli("doctor")[1]
            self.assertIn("orbitd hasn't loaded: fresh", out)
        finally:
            charon.stop()

    def test_peer_url_pointing_at_the_wrong_machine(self):
        charon = Machine(self.root, "charon", "pluto", 19780, 19780, FIXTURE_CAPS)  # peer_url points at itself
        charon.start()
        try:
            out = charon.cli("doctor")[1]
            self.assertIn("✗ peer_url points at charon, expected pluto", out)
        finally:
            charon.stop()

    def test_capability_mismatch_between_machines(self):
        empty = self.root / "empty"
        empty.mkdir()
        charon = Machine(self.root, "charon", "pluto", 19780, 19781, FIXTURE_CAPS)
        pluto = Machine(self.root, "pluto", "charon", 19781, 19780, empty)
        charon.start()
        pluto.start()
        try:
            out = charon.cli("doctor")[1]
            self.assertIn("only on charon: ping — install it on pluto too", out)
        finally:
            charon.stop()
            pluto.stop()


class DevPeerTest(unittest.TestCase):
    def test_dev_peer_writes_a_mirrored_config_and_runs_commands_as_the_peer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config.write(root / "me", {"me": "charon", "peer": "pluto", "port": 1978})
            def quiet_call(cmd, **kw):  # the child writes to the real fd 1; keep test output clean
                return subprocess.run(cmd, capture_output=True, **kw).returncode

            with mock.patch.dict(os.environ, {"ORBIT_DEVPEER_DIR": str(root / "peer")}), \
                    mock.patch.object(devtools.subprocess, "call", quiet_call):
                code, _, _ = run_cli(root / "me", "dev", "peer", "help")
            self.assertEqual(code, 0)
            peer = config.load(root / "peer")
            self.assertEqual((peer.me, peer.peer, peer.port), ("pluto", "charon", 1979))
            self.assertEqual(peer.peer_url, "http://127.0.0.1:1978")
            self.assertEqual(peer.dev_allow_ips, ["127.0.0.1"])
