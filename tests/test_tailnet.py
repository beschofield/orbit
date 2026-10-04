import json
import socket
import subprocess
import unittest
from unittest import mock

from orbit import tailnet


def status(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["tailscale"], returncode, stdout=stdout, stderr="")


def addrinfo(*addresses: str) -> list:
    return [(socket.AF_INET6 if ":" in a else socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0)) for a in addresses]


class TailnetTest(unittest.TestCase):
    def test_suffix_comes_from_tailscale_status(self):
        out = json.dumps({"MagicDNSSuffix": "tail123.ts.net", "CurrentTailnet": {"MagicDNSEnabled": True}})
        with mock.patch.object(tailnet.subprocess, "run", return_value=status(out)):
            self.assertEqual(tailnet.magicdns_suffix(), "tail123.ts.net")

    def test_no_suffix_when_magicdns_is_off_or_tailscale_is_missing(self):
        off = json.dumps({"MagicDNSSuffix": "tail123.ts.net", "CurrentTailnet": {"MagicDNSEnabled": False}})
        for result in (status(off), status("", returncode=1), status("not json")):
            with mock.patch.object(tailnet.subprocess, "run", return_value=result):
                self.assertIsNone(tailnet.magicdns_suffix())
        with mock.patch.object(tailnet.subprocess, "run", side_effect=FileNotFoundError("tailscale")):
            self.assertIsNone(tailnet.magicdns_suffix())

    def test_tailnet_ranges(self):
        for a in ("100.74.73.29", "100.64.0.1", "fd7a:115c:a1e0::1"):
            self.assertTrue(tailnet.is_tailnet_ip(a), a)
        for a in ("192.168.4.45", "fe80::1%eth0", "2600:1700::1", "127.0.0.1", "charon"):
            self.assertFalse(tailnet.is_tailnet_ip(a), a)

    def test_lan_answers_for_a_bare_name_are_reported(self):  # what pluto saw: LLMNR beat MagicDNS
        lan = addrinfo("192.168.4.45", "fe80::be24:11ff:fea8:12ca", "192.168.4.45")
        with mock.patch.object(tailnet.socket, "getaddrinfo", return_value=lan):
            self.assertEqual(tailnet.off_tailnet_addresses("charon"), ["192.168.4.45", "fe80::be24:11ff:fea8:12ca"])

    def test_tailnet_answers_ip_literals_and_unresolvable_names_are_fine(self):
        with mock.patch.object(tailnet.socket, "getaddrinfo", return_value=addrinfo("100.74.73.29")):
            self.assertEqual(tailnet.off_tailnet_addresses("charon.tail123.ts.net"), [])
        with mock.patch.object(tailnet.socket, "getaddrinfo", side_effect=socket.gaierror("nope")):
            self.assertEqual(tailnet.off_tailnet_addresses("charon"), [])
        self.assertEqual(tailnet.off_tailnet_addresses("127.0.0.1"), [])  # typed on purpose
