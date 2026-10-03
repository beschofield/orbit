"""Runs every real capability's tests/*.json cases, so `python3 -m unittest` covers them."""
import unittest

from orbit import contract, devtools
from tests.helpers import REPO


class CapabilityCasesTest(unittest.TestCase):
    def test_every_capability_has_a_readme_and_passing_cases(self):
        folders = sorted(p for p in (REPO / "capabilities").iterdir()
                         if p.is_dir() and not p.name.startswith((".", "_")))
        self.assertTrue(folders)
        for d in folders:
            with self.subTest(capability=d.name):
                m = contract.parse_manifest(d / "manifest.json")
                count, failures = devtools.run_cases(m)
                self.assertGreater(count, 0, f"{d.name} has no tests/*.json cases")
                self.assertEqual(failures, [], "\n".join(failures))
                self.assertTrue((d / "README.md").is_file(), f"{d.name} needs a README.md")
