import os
import pty
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

    def bash(self, script: str, path: str | None = None, tty: bool = False) -> subprocess.CompletedProcess:
        """Run an interactive bash. tty=True gives it a terminal on stdout, as a real login has."""
        env = {"HOME": str(self.home), "PATH": path or f"{self.bin}:/usr/bin:/bin", "TERM": "dumb"}
        if not tty:
            return subprocess.run(["bash", "-i", "-c", script], env=env, capture_output=True, text=True, timeout=10)
        master, slave = pty.openpty()
        try:
            r = subprocess.run(["bash", "-i", "-c", script], env=env, stdin=subprocess.DEVNULL, stdout=slave,
                               stderr=subprocess.PIPE, text=True, timeout=10)
        finally:
            os.close(slave)
        chunks = []
        try:
            while chunk := os.read(master, 4096):
                chunks.append(chunk)
        except OSError:  # EIO once the terminal is drained
            pass
        finally:
            os.close(master)
        r.stdout = b"".join(chunks).decode("utf-8", "replace").replace("\r\n", "\n")
        return r

    def test_prompt_reads_the_file_and_never_runs_orbit(self):
        (self.home / ".orbit" / "prompt").write_text("♇ pluto: idle", encoding="utf-8")
        r = self.bash('__orbit_prompt; __orbit_prompt; __orbit_prompt; printf "[%s]" "$ORBIT_PS"', tty=True)
        self.assertIn("[♇ pluto: idle]", r.stdout)
        self.assertEqual(self.calls.read_text().splitlines(), ["greet"])  # only the login greeting

    def test_missing_prompt_file_gives_an_empty_segment(self):
        r = self.bash('__orbit_prompt; printf "[%s]" "$ORBIT_PS"')
        self.assertIn("[]", r.stdout)

    def test_prompt_hook_keeps_the_exit_status(self):
        (self.home / ".orbit" / "prompt").write_text("x", encoding="utf-8")
        self.assertIn("st=1", self.bash('false; __orbit_prompt; echo "st=$?"').stdout)
        (self.home / ".orbit" / "prompt").unlink()
        self.assertIn("st=0", self.bash('true; __orbit_prompt; echo "st=$?"').stdout)
        self.assertIn("st=3", self.bash('(exit 3); __orbit_prompt; echo "st=$?"').stdout)

    def test_greet_uses_the_installed_orbit_even_when_path_is_stale(self):
        local_bin = self.home / ".local" / "bin"
        local_bin.mkdir(parents=True)
        fake(local_bin, "orbit", f'echo "local $@" >> {self.calls}')
        self.bash("echo ready", path="/usr/bin:/bin", tty=True)  # neither bin folder on PATH
        self.assertEqual(self.calls.read_text().splitlines(), ["local greet"])

    def test_greet_is_skipped_when_stdout_is_not_a_terminal(self):
        self.bash("echo ready")  # capture_output: stdout is a pipe
        self.assertFalse(self.calls.exists())

    def test_sourcing_twice_adds_hooks_once(self):  # Review Focus #2
        r = self.bash('source ~/.bashrc; printf "%s\\n" "$PS1" "$PROMPT_COMMAND"')
        self.assertEqual(r.stdout.count("${ORBIT_PS:+"), 1, r.stdout)
        self.assertEqual(r.stdout.count("__orbit_prompt"), 1, r.stdout)

    def test_without_orbit_installed_the_shell_still_starts(self):
        r = self.bash("echo ready", path="/usr/bin:/bin", tty=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("ready", r.stdout)
        self.assertFalse(self.calls.exists())


class InstallTest(unittest.TestCase):
    """Runs install.sh against a temporary HOME with fake tailscale and systemctl."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        (self.home / ".orbit").mkdir(parents=True)
        (self.home / ".orbit" / "config.json").write_text('{"me": "charon", "peer": "pluto"}')
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.systemctl_log = self.root / "systemctl.log"
        fake(self.bin, "tailscale", "exit 0")
        fake(self.bin, "systemctl", f'echo "$@" >> {self.systemctl_log}')

    def tearDown(self):
        self.tmp.cleanup()

    def install(self) -> subprocess.CompletedProcess:
        env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin", "USER": "becca"}
        return subprocess.run(["bash", str(REPO / "install.sh")], env=env, capture_output=True,
                              text=True, timeout=30, stdin=subprocess.DEVNULL)

    def test_symlinked_bashrc_stays_a_symlink(self):
        dotfiles = self.root / "dotfiles"
        dotfiles.mkdir()
        (dotfiles / "bashrc").write_text("alias ll='ls -l'\n")
        (self.home / ".bashrc").symlink_to(dotfiles / "bashrc")
        for _ in range(2):
            self.assertEqual(self.install().returncode, 0)
        self.assertTrue((self.home / ".bashrc").is_symlink())
        self.assertEqual((dotfiles / "bashrc").read_text().count("# >>> orbit >>>"), 1)

    def test_half_a_block_is_left_alone_with_an_error(self):
        broken = "alias ll='ls -l'\n# >>> orbit >>>\nimportant stuff\n"
        (self.home / ".bashrc").write_text(broken)
        r = self.install()
        self.assertEqual(r.returncode, 1)
        self.assertIn("by hand", r.stderr)
        self.assertEqual((self.home / ".bashrc").read_text(), broken)
        self.assertFalse((self.home / ".local").exists())  # stopped before changing anything

    def test_install_twice_is_idempotent(self):  # Review Focus #2
        home, log = self.home, self.systemctl_log
        (home / ".bashrc").write_text("alias ll='ls -l'\n")
        for _ in range(2):
            r = self.install()
            self.assertEqual(r.returncode, 0, r.stderr)
        bashrc = (home / ".bashrc").read_text()
        self.assertEqual(bashrc.count("# >>> orbit >>>"), 1)
        self.assertIn("alias ll='ls -l'", bashrc)
        self.assertEqual((home / ".local" / "bin" / "orbit").resolve(), (REPO / "bin" / "orbit").resolve())
        self.assertTrue((home / ".config" / "systemd" / "user" / "orbitd.service").is_file())
        self.assertIn("--user enable --now orbitd.service", log.read_text())
        self.assertIn("loginctl enable-linger", r.stdout)
