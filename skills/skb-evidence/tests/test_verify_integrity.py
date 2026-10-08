"""verify._seed_integrity_failures: id 중복, 본문-해시 불일치, 스냅샷 부재, uri 부재를 잡는다."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import verify as V  # noqa: E402

TEXT = "첫 문단입니다.\n\n둘째 문단입니다."


def _note(text):
    return ("<!-- generated -->\n---\nid: evidence:seed:a_0000\nuri: https://e.com/a\n---\n\n"
            f"# T\n\n> Source: https://e.com/a\n\n{text}\n")


def _seed(text=TEXT, **kw):
    s = {"id": "evidence:seed:a_0000", "uri": "https://e.com/a", "md_path": "evidence/md/a_0000.md",
         "content_hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest()}
    s.update(kw)
    return s


class SeedIntegrityTest(unittest.TestCase):
    def run_check(self, seeds, note=None, deep=True):
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            if note is not None:
                (t / "evidence/md").mkdir(parents=True)
                (t / "evidence/md/a_0000.md").write_text(note, encoding="utf-8")
            return V._seed_integrity_failures(seeds, t, deep)

    def test_consistent_seed_passes(self):
        self.assertEqual(self.run_check([_seed()], _note(TEXT)), [])

    def test_duplicate_id_fails(self):
        f = self.run_check([_seed(), _seed()], _note(TEXT))
        self.assertTrue(any("duplicate seed id" in x for x in f))

    def test_hash_mismatch_fails(self):
        f = self.run_check([_seed()], _note(TEXT + " 변조"))
        self.assertTrue(any("does not match" in x for x in f))

    def test_shallow_skips_hash_check(self):
        self.assertEqual(self.run_check([_seed()], _note(TEXT + " 변조"), deep=False), [])

    def test_missing_uri_fails(self):
        f = self.run_check([_seed(uri="")], _note(TEXT))
        self.assertTrue(any("missing uri" in x for x in f))

    def test_snapshot_file_missing_fails(self):
        f = self.run_check([_seed(snapshot={"status": "ok", "pdf": "evidence/captures/x.pdf"})], _note(TEXT))
        self.assertTrue(any("snapshot pdf not found" in x for x in f))

    def test_failed_snapshot_is_not_checked(self):
        self.assertEqual(self.run_check([_seed(snapshot={"status": "error", "pdf": "gone.pdf"})], _note(TEXT)), [])


if __name__ == "__main__":
    unittest.main()


class OrphanMdNotesTest(unittest.TestCase):
    def test_orphan_md_notes_lists_unreferenced_notes_only(self):
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            md = t / "evidence" / "md"
            md.mkdir(parents=True)
            (md / "a_0000.md").write_text("x")
            (md / "b_0000.md").write_text("y")
            seeds = [{"id": "s", "md_path": "evidence/md/a_0000.md"}]
            self.assertEqual(V.orphan_md_notes(seeds, t), ["evidence/md/b_0000.md"])

    def test_orphan_md_notes_empty_when_all_referenced_or_no_dir(self):
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            self.assertEqual(V.orphan_md_notes([], t), [])
            md = t / "evidence" / "md"
            md.mkdir(parents=True)
            (md / "a.md").write_text("x")
            self.assertEqual(V.orphan_md_notes([{"md_path": "evidence/md/a.md"}], t), [])
