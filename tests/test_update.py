"""`orbit update` against a throwaway origin and clone. Never touches the real repo, ~/.orbit or systemd:
ORBIT_DIR points at an empty temp folder and a fake `systemctl` on PATH records its arguments."""
import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from orbit import daemon, doctor, update
from tests.helpers import make_runtime, run_cli


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        gitconfig = root / "gitconfig"
        gitconfig.write_text("[user]\n\tname = Test\n\temail = test@example.com\n"
                             "[init]\n\tdefaultBranch = main\n", encoding="utf-8")
        fake_bin = root / "bin"
        fake_bin.mkdir()
        self.systemctl_log = root / "systemctl.log"
        systemctl = fake_bin / "systemctl"
        systemctl.write_text(f'#!/bin/sh\necho "$@" >> {self.systemctl_log}\n', encoding="utf-8")
        systemctl.chmod(0o755)
        env = mock.patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": str(gitconfig), "GIT_CONFIG_NOSYSTEM": "1",
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "ORBIT_DIR": str(root / "no-config"), "NO_COLOR": "1"})
        env.start()
        self.addCleanup(env.stop)

        self.origin, self.upstream, self.clone = root / "origin.git", root / "upstream", root / "clone"
        self.git(root, "init", "--bare", str(self.origin))
        self.git(root, "clone", str(self.origin), str(self.upstream))
        self.commit(self.upstream, {"orbit/core.py": "v1\n", "capabilities/notes/main.py": "v1\n"}, "first")
        self.git(self.upstream, "push", "origin", "HEAD")
        self.git(root, "clone", str(self.origin), str(self.clone))

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, repo: Path, files: dict[str, str], message: str, push: bool = False) -> None:
        for name, text in files.items():
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            (repo / name).write_text(text, encoding="utf-8")
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-m", message)
        if push:
            self.git(repo, "push", "origin", "HEAD")

    def update(self) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = update.main([], repo=self.clone, doctor=False)
        return code, out.getvalue(), err.getvalue()

    def restarts(self) -> list[str]:
        return self.systemctl_log.read_text().splitlines() if self.systemctl_log.exists() else []

    def head(self) -> str:
        return self.git(self.clone, "rev-parse", "HEAD")

    def test_already_up_to_date(self):
        code, out, _ = self.update()
        self.assertEqual(code, 0)
        self.assertIn("already up to date", out)
        self.assertEqual(self.restarts(), [])

    def test_capability_only_change_does_not_restart(self):
        self.commit(self.upstream, {"capabilities/notes/main.py": "v2\n"}, "notes: v2", push=True)
        code, out, _ = self.update()
        self.assertEqual(code, 0, out)
        self.assertIn("notes: v2", out)
        self.assertIn("no restart needed", out)
        self.assertEqual(self.restarts(), [])
        self.assertEqual((self.clone / "capabilities/notes/main.py").read_text(), "v2\n")

    def test_core_change_restarts_orbitd(self):
        self.commit(self.upstream, {"orbit/core.py": "v2\n"}, "core: v2", push=True)
        code, out, _ = self.update()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.restarts(), ["--user restart orbitd"])
        self.assertIn("restarted orbitd", out)
        self.assertIn("Fresh code, same orbit", out)

    def test_shell_change_suggests_install(self):
        self.commit(self.upstream, {"shell/orbit.bash": "# new\n"}, "shell", push=True)
        _, out, _ = self.update()
        self.assertIn("install.sh", out)
        self.assertEqual(self.restarts(), ["--user restart orbitd"])

    def test_dirty_tree_is_refused_and_nothing_changes(self):
        self.commit(self.upstream, {"orbit/core.py": "v2\n"}, "core: v2", push=True)
        (self.clone / "orbit/core.py").write_text("my edit\n", encoding="utf-8")
        before = self.head()
        code, _, err = self.update()
        self.assertEqual(code, 1)
        self.assertIn("you have local changes", err)
        self.assertEqual(self.head(), before)
        self.assertEqual((self.clone / "orbit/core.py").read_text(), "my edit\n")
        self.assertEqual(self.restarts(), [])

    def test_diverged_branch_is_refused_with_the_hint(self):
        self.commit(self.upstream, {"orbit/core.py": "theirs\n"}, "theirs", push=True)
        self.commit(self.clone, {"capabilities/notes/main.py": "mine\n"}, "mine")
        before = self.head()
        code, _, err = self.update()
        self.assertEqual(code, 1)
        self.assertIn("diverged", err)
        self.assertIn("pull --rebase", err)
        self.assertEqual(self.head(), before)
        self.assertEqual(self.restarts(), [])

    def test_no_systemd_prints_the_command(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertIn("systemctl --user restart orbitd", update.restart_daemon(None))

    def test_extra_arguments_print_usage(self):
        code, _, err = run_cli(Path(self.tmp.name) / "no-config", "update", "now")
        self.assertEqual(code, 2)
        self.assertIn("usage: orbit update", err)

    def test_doctor_names_the_machine_that_is_behind(self):
        old = self.git(self.clone, "rev-parse", "--short", "HEAD")
        self.commit(self.upstream, {"orbit/core.py": "v2\n"}, "core: v2", push=True)
        new = self.git(self.upstream, "rev-parse", "--short", "HEAD")
        # pluto has pushed new code this clone hasn't fetched: charon is behind
        self.assertIn("run `orbit update` on charon", doctor.commit_mismatch("charon", "pluto", old, new, self.clone))
        self.git(self.clone, "pull", "--ff-only")
        self.assertIn("run `orbit update` on pluto", doctor.commit_mismatch("charon", "pluto", new, old, self.clone))
        self.assertIsNone(doctor.commit_mismatch("charon", "pluto", new, new, self.clone))
        self.assertIsNone(doctor.commit_mismatch("charon", "pluto", new, None, self.clone))

    def test_health_reports_the_commit(self):
        rt = make_runtime(Path(self.tmp.name) / "data", Path(self.tmp.name) / "caps")
        try:
            self.assertEqual(daemon.health(rt)["commit"], update.current_commit())
        finally:
            rt.store.close()
        self.assertIsNone(update.current_commit(Path(self.tmp.name)))  # not a git checkout


if __name__ == "__main__":
    unittest.main()
