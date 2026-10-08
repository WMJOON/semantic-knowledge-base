"""verify 의 카탈로그 연동과 list_seeds --catalog."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
VENV_PY = Path(__file__).resolve().parents[2] / "skb-ontology" / ".venv" / "bin" / "python"
PY = str(VENV_PY) if VENV_PY.exists() else sys.executable
HAVE = subprocess.run([PY, "-c", "import rdflib, pyshacl"], capture_output=True).returncode == 0


def seed(i, uri, body):
    import hashlib
    return {"id": f"evidence:seed:d{i}_0000", "kind": "url", "uri": uri, "retrieved_at": "2026-09-30T01:02:03Z",
            "content_hash": "sha256:" + hashlib.sha256(body.encode()).hexdigest(), "title": f"T{i}",
            "chunk": {"index": 0, "total": 1, "char_start": 0, "char_end": len(body)}, "claims": [], "status": "collected",
            "md_path": f"evidence/md/d{i}_0000.md", "tool_version": "skb-evidence/1.2.3",
            "retrieval": {"request_url": uri, "method": "GET", "status": 200}}


@unittest.skipUnless(HAVE, "rdflib/pyshacl 필요")
class ReadersTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.t = Path(self.td.name)
        (self.t / "evidence/md").mkdir(parents=True)
        rows = []
        for i, u in enumerate(["https://arxiv.org/abs/1", "https://blog.example.com/p"]):
            body = f"chunk body {i}"
            (self.t / f"evidence/md/d{i}_0000.md").write_text(f"---\nid: x\n---\n\n# t\n\n{body}\n", encoding="utf-8")
            rows.append(seed(i, u, body))
        self.write_seeds(rows)
        self.rows = rows
        self.build()

    def tearDown(self):
        self.td.cleanup()

    def write_seeds(self, rows):
        (self.t / "evidence/seeds.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    def build(self):
        r = subprocess.run([PY, str(SCRIPTS / "catalog.py"), "--target", str(self.t), "--apply"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def verify(self, *a):
        return subprocess.run([PY, str(SCRIPTS / "verify.py"), "--target", str(self.t), "--shallow", *a], capture_output=True, text=True)

    def ls(self, *a):
        return subprocess.run([PY, str(SCRIPTS / "list_seeds.py"), "--target", str(self.t), *a], capture_output=True, text=True)

    def test_verify_passes_with_valid_catalog(self):
        r = self.verify()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("WARN", r.stderr)

    def test_verify_reports_catalog_violation(self):
        p = self.t / "evidence/catalog/catalog.ttl"
        lines = p.read_text(encoding="utf-8").split("\n")
        i = next(k for k, ln in enumerate(lines) if ln.strip().startswith("dcterms:publisher"))
        del lines[i]
        p.write_text("\n".join(lines), encoding="utf-8")
        r = self.verify()
        self.assertEqual(r.returncode, 1)
        self.assertIn("catalog:", r.stderr)
        self.assertEqual(self.verify("--no-catalog").returncode, 0)   # 끌 수 있다

    def test_verify_warns_when_catalog_is_stale(self):
        body = "late chunk"
        (self.t / "evidence/md/d9_0000.md").write_text(f"---\nid: x\n---\n\n# t\n\n{body}\n", encoding="utf-8")
        self.write_seeds(self.rows + [seed(9, "https://late.example.org/x", body)])
        r = self.verify()
        self.assertEqual(r.returncode, 0)                 # 경고일 뿐 실패가 아니다
        self.assertIn("어긋났다", r.stderr)

    def test_verify_without_catalog_is_unchanged(self):
        import shutil
        shutil.rmtree(self.t / "evidence/catalog")
        r = self.verify()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("catalog", r.stderr)

    def test_list_catalog_table_json_ids(self):
        t = self.ls("--catalog")
        self.assertEqual(t.returncode, 0, t.stderr)
        self.assertIn("arXiv", t.stdout)
        self.assertIn("Total: 2 source(s), 2 chunk(s)", t.stdout)
        j = json.loads(self.ls("--catalog", "--format", "json").stdout)
        self.assertEqual(sorted(x["url"] for x in j), ["https://arxiv.org/abs/1", "https://blog.example.com/p"])
        self.assertTrue(all(x["retrieved_at"] for x in j))
        self.assertEqual(self.ls("--catalog", "--format", "ids").stdout.split(), ["evidence:seed:d0", "evidence:seed:d1"])

    def test_list_catalog_without_catalog_fails_with_hint(self):
        import shutil
        shutil.rmtree(self.t / "evidence/catalog")
        r = self.ls("--catalog")
        self.assertEqual(r.returncode, 1)
        self.assertIn("catalog --apply", r.stderr)

    def test_list_default_still_lists_seed_rows(self):
        r = self.ls()
        self.assertIn("Total: 2 seed(s)", r.stdout)


if __name__ == "__main__":
    unittest.main()
