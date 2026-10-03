import json
import re
import unittest
from pathlib import Path

from orbit import contract
from tests.helpers import REPO

DOC = REPO / "docs" / "capability-contract.md"
BLOCK = re.compile(r"```json (manifest|input|output|case)\n(.*?)```", re.S)


class ContractDocTest(unittest.TestCase):
    def blocks(self, kind: str) -> list:
        return [json.loads(body) for k, body in BLOCK.findall(DOC.read_text(encoding="utf-8")) if k == kind]

    def first_manifest(self) -> contract.Manifest:
        data = self.blocks("manifest")[0]
        return contract.manifest_from_dict(data, Path("/doc") / data["name"], "doc manifest", check_files=False)

    def test_doc_has_each_kind_of_example(self):
        for kind in ("manifest", "input", "output", "case"):
            self.assertTrue(self.blocks(kind), f"no ```json {kind} block in {DOC}")

    def test_manifest_examples_are_valid(self):
        for data in self.blocks("manifest"):
            contract.manifest_from_dict(data, Path("/doc") / data["name"], "doc manifest", check_files=False)

    def test_output_examples_are_valid(self):
        m = self.first_manifest()
        for data in self.blocks("output"):
            contract.output_from_dict(data, m, "doc output")
        for case in self.blocks("case"):
            if any(k in case["expect"] for k in ("say", "emit", "prompt")):
                contract.output_from_dict({k: v for k, v in case["expect"].items() if v is not None}, m, "doc case")

    def test_input_example_has_every_field(self):
        for data in self.blocks("input"):
            self.assertEqual(set(data), {"contract", "trigger", "me", "peer", "now", "events", "latest"})

    def test_limits_and_names_in_doc_match_code(self):
        text = DOC.read_text(encoding="utf-8")
        for n in (contract.MAX_SAY_CHARS, contract.MAX_PROMPT_CHARS, contract.MIN_TICK_SECONDS):
            self.assertIn(str(n), text)
        for word in contract.MOODS + contract.TRIGGERS:
            self.assertIn(f"`{word}`", text)
        for name in contract.RESERVED_COMMANDS:
            self.assertIn(f"`{name}`", text)
