import re
import unittest

from tests.helpers import REPO


class DocsTest(unittest.TestCase):
    def test_claude_md_is_short_and_points_to_the_contract_and_skill(self):
        text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertLess(len(text.splitlines()), 150)
        for needle in ("docs/capability-contract.md", "new-capability", "python3 -m unittest", "orbit dev test",
                       "orbit doctor", "stdlib", "girlfriend"):
            self.assertIn(needle, text)
        self.assertNotIn("partner", text.lower())

    def test_every_module_is_in_the_claude_md_map(self):
        text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
        for module in sorted((REPO / "orbit").glob("*.py")):
            if module.name != "__init__.py":
                self.assertIn(f"orbit/{module.name}", text)

    def test_skill_has_frontmatter_and_the_steps(self):
        text = (REPO / ".claude" / "skills" / "new-capability" / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(re.match(r"---\nname: new-capability\ndescription: .+\n---\n", text))
        for needle in ("cp -r capabilities/example", "tests/", "orbit dev test", "orbit dev run", "both machines"):
            self.assertIn(needle, text)

    def test_no_doc_says_partner(self):
        for path in [REPO / "README.md", REPO / "docs" / "reveal-day.md", *(REPO / "capabilities").glob("*/README.md")]:
            self.assertNotIn("partner", path.read_text(encoding="utf-8").lower(), path)
