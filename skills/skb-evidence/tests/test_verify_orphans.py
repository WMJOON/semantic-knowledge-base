"""verify.orphan_md_notes: seed 가 가리키지 않는 evidence/md 노트만 골라낸다."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import verify as V  # noqa: E402


class OrphanMdNotesTest(unittest.TestCase):
    def test_lists_unreferenced_notes_only(self):
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            md = t / "evidence" / "md"
            md.mkdir(parents=True)
            (md / "a_0000.md").write_text("x")
            (md / "b_0000.md").write_text("y")
            seeds = [{"id": "s", "md_path": "evidence/md/a_0000.md"}]
            self.assertEqual(V.orphan_md_notes(seeds, t), ["evidence/md/b_0000.md"])

    def test_empty_when_all_referenced_or_no_dir(self):
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            self.assertEqual(V.orphan_md_notes([], t), [])
            md = t / "evidence" / "md"
            md.mkdir(parents=True)
            (md / "a.md").write_text("x")
            self.assertEqual(V.orphan_md_notes([{"md_path": "evidence/md/a.md"}], t), [])


if __name__ == "__main__":
    unittest.main()
