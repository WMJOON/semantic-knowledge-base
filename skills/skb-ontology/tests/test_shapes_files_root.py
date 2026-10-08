"""ttl_common.shapes_files: semantic 루트 직속 shapes(KB 전역 규약)가 도메인 실행에도 포함되는지 확인한다."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ttl_common  # noqa: E402


class ShapesFilesRootTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.kb = Path(self.td.name)
        root = ttl_common.semantic_root(self.kb)
        (root / "a").mkdir(parents=True)
        (root / "b").mkdir(parents=True)
        (root / "kb-global.shapes.ttl").write_text("# global\n")
        (root / "a" / "a.shapes.ttl").write_text("# a\n")
        (root / "b" / "b.shapes.ttl").write_text("# b\n")
        self.root = root

    def tearDown(self):
        self.td.cleanup()

    def names(self, domain):
        return sorted(p.name for p in ttl_common.shapes_files(self.kb, domain))

    def test_whole_kb_run_includes_everything_once(self):
        self.assertEqual(self.names(None), ["a.shapes.ttl", "b.shapes.ttl", "kb-global.shapes.ttl"])

    def test_domain_run_includes_own_and_root_shapes_only(self):
        self.assertEqual(self.names("a"), ["a.shapes.ttl", "kb-global.shapes.ttl"])

    def test_domain_run_does_not_leak_other_domains(self):
        self.assertNotIn("b.shapes.ttl", self.names("a"))

    def test_missing_domain_still_gets_root_shapes(self):
        self.assertEqual(self.names("nope"), ["kb-global.shapes.ttl"])


if __name__ == "__main__":
    unittest.main()
