"""catalog 빌드·검증: 정상 통과, raw provenance 전파, 변조·형상 위반이 실제로 잡히는지(긍정·부정)."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
VENV_PY = Path(__file__).resolve().parents[2] / "skb-ontology" / ".venv" / "bin" / "python"
PY = str(VENV_PY) if VENV_PY.exists() else sys.executable

HAVE = subprocess.run([PY, "-c", "import rdflib, pyshacl"], capture_output=True).returncode == 0

RAW = (
    "---\nsource: https://arxiv.org/abs/1\ncollected_at: 2026-09-30T01:02:03Z\ncollected_at_basis: fetch-time\n"
    "published_at: 2026-04-14\npublished_at_source: arxiv:citation_date\npublisher: arXiv\npublisher_source: domain-derived\n"
    "publisher_type: Organization\npublisher_type_source: none:x\n"
    'authors: [{"name": "Jane Doe"}]\nauthors_source: meta:citation_author\naccounts: []\naccounts_source: none:no-platform-account\n'
    "document_type: paper\ndocument_type_source: meta:citation_*\nconverter: docling\n---\n\nbody\n"
)
RAW_NODATE = RAW.replace("source: https://arxiv.org/abs/1", "source: https://blog.example.com/p").replace(
    "published_at: 2026-04-14", "published_at: unavailable").replace("arxiv:citation_date", "none:no-declared-date").replace(
    'authors: [{"name": "Jane Doe"}]', "authors: []").replace("meta:citation_author", "none:no-declared-author")


def seed(i, uri, h):
    return {"id": f"evidence:seed:s{i}_0000", "kind": "url", "uri": uri, "retrieved_at": "2026-09-30T01:02:03Z",
            "content_hash": "sha256:" + h * 64, "title": f"T{i}", "chunk": {"index": 0, "total": 1, "char_start": 0, "char_end": 500},
            "claims": [], "status": "collected", "md_path": f"evidence/md/s{i}_0000.md", "tool_version": "skb-evidence/1.2.0"}


@unittest.skipUnless(HAVE, "rdflib/pyshacl 필요")
class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.t = Path(self.td.name)
        (self.t / "evidence/raw").mkdir(parents=True)
        (self.t / "evidence/raw/a.md").write_text(RAW, encoding="utf-8")
        (self.t / "evidence/raw/b.md").write_text(RAW_NODATE, encoding="utf-8")
        with open(self.t / "evidence/seeds.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps(seed(1, "https://arxiv.org/abs/1", "a")) + "\n")
            f.write(json.dumps(seed(2, "https://blog.example.com/p", "b")) + "\n")
            f.write(json.dumps(seed(3, "https://other.example.org/x", "c")) + "\n")  # raw 없음
        self.build()

    def tearDown(self):
        self.td.cleanup()

    def build(self):
        return subprocess.run([PY, str(SCRIPTS / "catalog.py"), "--target", str(self.t), "--apply"], capture_output=True, text=True)

    def validate(self):
        return subprocess.run([PY, str(SCRIPTS / "catalog_validate.py"), "--target", str(self.t)], capture_output=True, text=True)

    def ttl(self):
        return (self.t / "evidence/catalog/catalog.ttl").read_text(encoding="utf-8")

    def test_dry_run_writes_nothing(self):
        shutil.rmtree(self.t / "evidence/catalog")
        r = subprocess.run([PY, str(SCRIPTS / "catalog.py"), "--target", str(self.t)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertFalse((self.t / "evidence/catalog").exists())

    def test_built_catalog_passes(self):
        r = self.validate()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_build_is_deterministic(self):
        first = self.ttl()
        self.build()
        self.assertEqual(first, self.ttl())

    def test_raw_provenance_propagates(self):
        t = self.ttl()
        self.assertIn('dcterms:issued "2026-04-14"^^xsd:date', t)
        self.assertIn('ec:publishedAtSource "arxiv:citation_date"', t)
        self.assertIn('ec:authorRaw "Jane Doe"', t)

    def test_unavailable_date_keeps_reason_without_issued(self):
        t = self.ttl()
        self.assertIn('ec:publishedAtSource "none:no-declared-date"', t)
        self.assertEqual(t.count("dcterms:issued"), 1)

    def test_authorless_source_records_reason(self):
        self.assertIn('ec:authorshipReason "none:no-declared-author"', self.ttl())

    def test_source_without_raw_is_unresolved_not_failed(self):
        self.assertIn('ec:authorshipReason "not_extracted"', self.ttl())
        self.assertEqual(self.validate().returncode, 0)

    def test_changed_chunk_file_is_caught(self):
        p = self.t / "evidence/catalog/chunks.jsonl"
        rows = [r for r in p.read_text(encoding="utf-8").split("\n") if r][:-1]
        p.write_text("\n".join(rows) + "\n", encoding="utf-8")
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertTrue("rowCount" in r.stderr or "청크 수" in r.stderr or "sha256" in r.stderr)

    def test_missing_publisher_is_caught(self):
        p = self.t / "evidence/catalog/catalog.ttl"
        lines = p.read_text(encoding="utf-8").split("\n")
        i = next(k for k, ln in enumerate(lines) if ln.strip().startswith("dcterms:publisher"))
        del lines[i]
        p.write_text("\n".join(lines), encoding="utf-8")
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("SHACL", r.stderr)

    def test_issued_without_source_is_caught(self):
        p = self.t / "evidence/catalog/catalog.ttl"
        p.write_text(p.read_text(encoding="utf-8").replace('ec:publishedAtSource "arxiv:citation_date" ;', ""), encoding="utf-8")
        r = self.validate()
        self.assertEqual(r.returncode, 1)

    def test_deleted_raw_file_is_caught(self):
        (self.t / "evidence/raw/a.md").unlink()
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("rawPath", r.stderr)


@unittest.skipUnless(HAVE, "rdflib/pyshacl 필요")
class RetrievalTest(unittest.TestCase):
    """수집 시점 세 가지(searchedAt/retrievedAt/collectedAt)와 요청 조건, 청크 위치."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.t = Path(self.td.name)
        (self.t / "evidence/raw").mkdir(parents=True)
        (self.t / "evidence/raw/a.md").write_text(RAW.replace("2026-09-30T01:02:03Z", "2026-09-30T05:00:00Z"), encoding="utf-8")
        a = seed(1, "https://arxiv.org/abs/1", "a")
        a["retrieved_at"] = "2026-09-30T04:00:00Z"  # raw 의 collected_at(05:00)과 다르다
        a["retrieval"] = {"request_url": "https://arxiv.org/pdf/1", "method": "GET", "status": 200, "media_type": "application/pdf",
                          "response_sha256": "ab" * 32, "searched_at": "2026-09-30T03:00:00Z", "search_query": "chunking evaluation",
                          "params": {"v": "2"}}
        b = seed(2, "https://other.example.org/x", "b")
        with open(self.t / "evidence/seeds.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps(a) + "\n" + json.dumps(b) + "\n")
        subprocess.run([PY, str(SCRIPTS / "catalog.py"), "--target", str(self.t), "--apply"], capture_output=True, text=True)

    def tearDown(self):
        self.td.cleanup()

    def ttl(self):
        return (self.t / "evidence/catalog/catalog.ttl").read_text(encoding="utf-8")

    def validate(self):
        return subprocess.run([PY, str(SCRIPTS / "catalog_validate.py"), "--target", str(self.t)], capture_output=True, text=True)

    def edit(self, old, new):
        p = self.t / "evidence/catalog/catalog.ttl"
        t = p.read_text(encoding="utf-8")
        self.assertIn(old, t)
        p.write_text(t.replace(old, new, 1), encoding="utf-8")

    def test_three_times_are_kept_apart(self):
        t = self.ttl()
        self.assertIn('ec:retrievedAt "2026-09-30T04:00:00+00:00"^^xsd:dateTime', t)   # seed 값, raw 의 collected_at 으로 덮이지 않는다
        self.assertIn('ec:collectedAt "2026-09-30T05:00:00+00:00"^^xsd:dateTime', t)   # raw 선언값
        self.assertIn('ec:searchedAt "2026-09-30T03:00:00+00:00"^^xsd:dateTime', t)
        self.assertIn('ec:searchQuery "chunking evaluation"', t)
        self.assertNotIn("generatedAtTime", t)
        self.assertEqual(self.validate().returncode, 0)

    def test_request_conditions_recorded_and_url_per_source(self):
        t = self.ttl()
        self.assertIn('ec:requestUrl "https://arxiv.org/pdf/1"^^xsd:anyURI', t)   # 정규 주소(abs)와 다른 실제 다운로드 URL
        self.assertIn('ec:requestMethod "GET"', t)
        self.assertIn('ec:httpStatus 200', t)
        self.assertIn('ec:mediaType "application/pdf"', t)
        self.assertIn('ec:requestParams "{\\"v\\": \\"2\\"}"', t)
        self.assertIn('ec:requestUrl "https://other.example.org/x"^^xsd:anyURI', t)  # 요청 조건이 없으면 문서 URL

    def test_searched_only_when_found_by_search(self):
        self.assertEqual(self.ttl().count("ec:searchedAt"), 1)   # 직접 지정한 URL 에는 검색 시각이 없다

    def test_chunk_rows_keep_position(self):
        rows = [json.loads(x) for x in (self.t / "evidence/catalog/chunks.jsonl").read_text(encoding="utf-8").splitlines() if x]
        self.assertTrue(all("char_start" in r and "char_end" in r and r["char_len"] == r["char_end"] - r["char_start"] for r in rows))
        self.assertIn('ec:offsetBase "converted_text"', self.ttl())

    def test_searched_after_retrieved_is_caught(self):
        self.edit('ec:searchedAt "2026-09-30T03:00:00+00:00"', 'ec:searchedAt "2099-01-01T00:00:00Z"')
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("발견", r.stderr)

    def test_searched_without_query_is_caught(self):
        self.edit('ec:searchQuery "chunking evaluation"', 'ec:profileNote "x"')
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("searchQuery", r.stderr)

    def test_missing_retrieved_at_is_caught(self):
        self.edit('ec:retrievedAt "2026-09-30T04:00:00+00:00"^^xsd:dateTime', 'ec:collectedAtBasis "x"')
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("retrievedAt", r.stderr)

    def test_collected_basis_without_collected_at_is_caught(self):
        self.edit('ec:collectedAt "2026-09-30T05:00:00+00:00"^^xsd:dateTime ;', "")
        r = self.validate()
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
