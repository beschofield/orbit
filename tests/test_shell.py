import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO

SNIPPET = (REPO / "shell" / "orbit.bash").read_text(encoding="utf-8") if (REPO / "shell" / "orbit.bash").exists() else ""


def fake(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


class ShellSnippetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home = root / "home"
        (self.home / ".orbit").mkdir(parents=True)
        self.bin = root / "bin"
        self.bin.mkdir()
        self.calls = root / "calls"
        fake(self.bin, "orbit", f'echo "$@" >> {self.calls}')
        (self.home / ".bashrc").write_text("alias ll='ls -l'\n" + SNIPPET)

    def tearDown(self):
        self.tmp.cleanup()

    def bash(self, script: str, path: str | None = None) -> subprocess.CompletedProcess:
        env = {"HOME": str(self.home), "PATH": path or f"{self.bin}:/usr/bin:/bin", "TERM": "dumb"}
        return subprocess.run(["bash", "-i", "-c", script], env=env, capture_output=True, text=True, timeout=10)

    def test_prompt_reads_the_file_and_never_runs_orbit(self):
        (self.home / ".orbit" / "prompt").write_text("♇ pluto: idle", encoding="utf-8")
        r = self.bash('__orbit_prompt; __orbit_prompt; __orbit_prompt; printf "[%s]" "$ORBIT_PS"')
        self.assertIn("[♇ pluto: idle]", r.stdout)
        self.assertEqual(self.calls.read_text().splitlines(), ["greet"])  # only the login greeting

    def test_missing_prompt_file_gives_an_empty_segment(self):
        r = self.bash('__orbit_prompt; printf "[%s]" "$ORBIT_PS"')
        self.assertIn("[]", r.stdout)

    def test_sourcing_twice_adds_hooks_once(self):  # Review Focus #2
        r = self.bash('source ~/.bashrc; printf "%s\\n" "$PS1" "$PROMPT_COMMAND"')
        self.assertEqual(r.stdout.count("${ORBIT_PS:+"), 1, r.stdout)
        self.assertEqual(r.stdout.count("__orbit_prompt"), 1, r.stdout)

    def test_without_orbit_installed_the_shell_still_starts(self):
        r = self.bash("echo ready", path="/usr/bin:/bin")
        self.assertEqual(r.returncode, 0)
        self.assertIn("ready", r.stdout)
        self.assertFalse(self.calls.exists())


class InstallTest(unittest.TestCase):
    def test_install_twice_is_idempotent(self):  # Review Focus #2
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            (home / ".orbit").mkdir(parents=True)
            (home / ".orbit" / "config.json").write_text('{"me": "charon", "peer": "pluto"}')
            (home / ".bashrc").write_text("alias ll='ls -l'\n")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            log = root / "systemctl.log"
            fake(bin_dir, "tailscale", "exit 0")
            fake(bin_dir, "systemctl", f'echo "$@" >> {log}')
            env = {"HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin", "USER": "becca"}
            for _ in range(2):
                r = subprocess.run(["bash", str(REPO / "install.sh")], env=env, capture_output=True,
                                   text=True, timeout=30, stdin=subprocess.DEVNULL)
                self.assertEqual(r.returncode, 0, r.stderr)
            bashrc = (home / ".bashrc").read_text()
            self.assertEqual(bashrc.count("# >>> orbit >>>"), 1)
            self.assertIn("alias ll='ls -l'", bashrc)
            self.assertEqual((home / ".local" / "bin" / "orbit").resolve(), (REPO / "bin" / "orbit").resolve())
            self.assertTrue((home / ".config" / "systemd" / "user" / "orbitd.service").is_file())
            self.assertIn("--user enable --now orbitd.service", log.read_text())
            self.assertIn("loginctl enable-linger", r.stdout)
