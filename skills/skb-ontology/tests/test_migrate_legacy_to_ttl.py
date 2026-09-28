from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
CLI = SCRIPTS / "skb-ontology"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "abox_demo"
DEFINITION = FIXTURES / "definition" / "modeling.yaml"
ABOX = FIXTURES / "Abox" / "modeling.yaml"
SOURCE = "https://example.org/source/legacy-1"

sys.path.insert(0, str(SCRIPTS))

import migrate_legacy_to_ttl  # noqa: E402
from ttl_common import canonical_path, load_graph  # noqa: E402
from ttl_validate import validate_target  # noqa: E402


class MigrateLegacyToTTLTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.domain = "migrated"

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(CLI), "migrate-legacy",
             "--definition", str(DEFINITION),
             "--abox", str(ABOX),
             "--target", str(self.root),
             "--domain", self.domain,
             "--evidence", SOURCE,
             *extra],
            capture_output=True, text=True,
        )

    def test_dry_run_writes_nothing(self):
        result = self.run_cli()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("DRY RUN", result.stdout)
        path = canonical_path(self.root, self.domain)
        self.assertFalse(path.exists())

    def test_apply_writes_a_graph_that_passes_the_real_validator(self):
        result = self.run_cli("--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("APPLIED", result.stdout)

        path = canonical_path(self.root, self.domain)
        self.assertTrue(path.exists())

        paths, graph, failures = validate_target(self.root, self.domain)
        self.assertEqual([], failures)
        self.assertEqual([path], paths)

        graph = load_graph([path])
        names = {str(term).rsplit("/", 1)[-1] for term in graph.subjects()}
        for expected in ("Task", "ImageGeneration", "TransformerMLMModel", "MultimodalModel",
                          "canBeUsedFor", "gemma4E4b", "imageGenerationTask"):
            self.assertIn(expected, names, f"missing migrated term: {expected}")

    def test_evidence_is_required_by_the_cli(self):
        result = subprocess.run(
            [str(CLI), "migrate-legacy",
             "--definition", str(DEFINITION),
             "--abox", str(ABOX),
             "--target", str(self.root),
             "--domain", self.domain],
            capture_output=True, text=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("--evidence", result.stderr)

    def test_missing_evidence_produces_no_side_effects(self):
        # Direct API check: build_migration should refuse to run without evidence handling
        # left to the caller; the CLI enforces --evidence via argparse `required=True`.
        with self.assertRaises(SystemExit):
            migrate_legacy_to_ttl.main([
                "--definition", str(DEFINITION),
                "--abox", str(ABOX),
                "--target", str(self.root),
                "--domain", self.domain,
            ])
        path = canonical_path(self.root, self.domain)
        self.assertFalse(path.exists())

    def test_duplicate_migration_into_existing_domain_fails_loud(self):
        first = self.run_cli("--apply")
        self.assertEqual(0, first.returncode, first.stderr)

        second = self.run_cli("--apply")
        self.assertNotEqual(0, second.returncode)
        self.assertIn("duplicate migration target", second.stderr)

        # the original file must be untouched by the failed second attempt
        path = canonical_path(self.root, self.domain)
        _, _, failures = validate_target(self.root, self.domain)
        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
