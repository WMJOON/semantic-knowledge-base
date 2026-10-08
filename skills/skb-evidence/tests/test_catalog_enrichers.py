"""catalog 의 발행자 규칙(--publishers)과 도메인 enricher(legal-kr): 코어 밖 확장, locators, 규칙 우선순위, 위반 검출."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
VENV_PY = Path(__file__).resolve().parents[2] / "skb-ontology" / ".venv" / "bin" / "python"
PY = str(VENV_PY) if VENV_PY.exists() else sys.executable
HAVE = subprocess.run([PY, "-c", "import rdflib, pyshacl, yaml"], capture_output=True).returncode == 0

URL = "https://raw.githubusercontent.com/legalize-kr/legalize-kr/main/kr/%EC%86%8C%EB%93%9D%EC%84%B8%EB%B2%95/%EB%B2%95%EB%A5%A0.md"
URL2 = "https://raw.githubusercontent.com/someone/else/main/README.md"
RULES = """rules:
  - match: {host: raw.githubusercontent.com, path_prefix: /legalize-kr/legalize-kr/}
    publisher: {id: legalize-kr, name: legalize-kr 미러, kind: repository}
    issuer: {id: moleg, name: 법제처, kind: government}
"""
BODIES = [
    "# t\n\n##### 제1조 (목적) 가나다\n\n##### 제2조 (정의) 라마바",   # 머리 2개
    "① 제2조 본문이 이어진다",                                          # 머리 없이 시작 → 앞 청크의 제2조를 잇는다
    "##### 제3조 (적용) 사아자",                                         # 새 머리
]


def seed(sid, uri, i, body_path):
    return {"id": f"evidence:seed:{sid}_{i:04d}", "kind": "url", "uri": uri, "retrieved_at": "2026-09-30T01:02:03Z",
            "content_hash": "sha256:" + str(i) * 64, "title": "raw_githubusercontent_com_legal", "chunk": {"index": i, "total": 3, "char_start": i * 100, "char_end": i * 100 + 90},
            "claims": [], "status": "collected", "md_path": body_path, "tool_version": "skb-evidence/1.2.0"}


@unittest.skipUnless(HAVE, "rdflib/pyshacl/pyyaml 필요")
class EnricherTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.t = Path(self.td.name)
        (self.t / "evidence/md").mkdir(parents=True)
        rows = []
        for i, b in enumerate(BODIES):
            mp = f"evidence/md/law_{i:04d}.md"
            (self.t / mp).write_text(f"---\nid: x\n---\n{b}", encoding="utf-8")
            rows.append(seed("law", URL, i, mp))
        (self.t / "evidence/md/o_0000.md").write_text("---\nid: y\n---\nhello", encoding="utf-8")
        rows.append(seed("other", URL2, 0, "evidence/md/o_0000.md"))
        with open(self.t / "evidence/seeds.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        (self.t / "publishers.yaml").write_text(RULES, encoding="utf-8")

    def tearDown(self):
        self.td.cleanup()

    def build(self, *extra):
        return subprocess.run([PY, str(SCRIPTS / "catalog.py"), "--target", str(self.t), "--apply", *extra], capture_output=True, text=True)

    def validate(self):
        return subprocess.run([PY, str(SCRIPTS / "catalog_validate.py"), "--target", str(self.t)], capture_output=True, text=True)

    def ttl(self):
        return (self.t / "evidence/catalog/catalog.ttl").read_text(encoding="utf-8")

    def chunks(self):
        return [json.loads(x) for x in (self.t / "evidence/catalog/chunks.jsonl").read_text(encoding="utf-8").splitlines() if x]

    def full(self):
        r = self.build("--publishers", str(self.t / "publishers.yaml"), "--enricher", "legal-kr")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_without_enricher_core_stays_domain_free(self):
        self.assertEqual(self.build().returncode, 0)
        t = self.ttl()
        self.assertNotIn("lawName", t)
        self.assertNotIn("issuer", t)
        self.assertFalse(any("locators" in c for c in self.chunks()))
        self.assertEqual(self.validate().returncode, 0)

    def test_publisher_rule_splits_distributor_and_issuer(self):
        self.full()
        t = self.ttl()
        self.assertIn("publisher/legalize-kr", t)
        self.assertIn("ec:issuer <https://example.org/skb/evidence-catalog/publisher/moleg>", t)
        self.assertIn('ec:publisherKind "government"', t)
        self.assertIn('ec:curation "auto"', t)  # issuer 는 사람이 확정하기 전까지 auto
        self.assertEqual(self.validate().returncode, 0)

    def test_rule_only_matches_its_path_prefix(self):
        self.full()
        t = self.ttl()
        # 같은 호스트의 다른 저장소는 규칙에 걸리지 않고 호스트 도출(github)로 간다
        self.assertEqual(t.count("ec:issuer"), 1)
        self.assertIn("publisher/github", t)

    def test_law_name_comes_from_url_not_truncated_title(self):
        self.full()
        t = self.ttl()
        self.assertIn('ecl:lawName "소득세법"', t)
        self.assertIn('ecl:lawDocKind "법률"', t)
        self.assertIn('dcterms:title "소득세법 법률"', t)
        # 법령이 아닌 문서는 seed 의 title 을 그대로 둔다(법령 문서만 URL 에서 도출한 제목으로 바뀐다)
        self.assertEqual(t.count('dcterms:title "raw_githubusercontent_com_legal"'), 1)

    def test_commit_pinned_url_records_revision_and_main_url_does_not(self):
        import json as _j
        pinned = URL.replace("/main/", "/" + "a" * 40 + "/")
        rows = [_j.loads(x) for x in (self.t / "evidence/seeds.jsonl").read_text(encoding="utf-8").splitlines()]
        extra = dict(rows[0], id="evidence:seed:pinned_0000", uri=pinned)
        with open(self.t / "evidence/seeds.jsonl", "a", encoding="utf-8") as f:
            f.write(_j.dumps(extra) + "\n")
        self.full()
        t = self.ttl()
        self.assertEqual(t.count("ecl:sourceRevision"), 1)               # 고정 URL 만
        self.assertIn('ecl:sourceRevision "' + "a" * 40 + '"', t)
        self.assertEqual(self.validate().returncode, 0)

    def test_extension_schema_is_copied_and_used(self):
        self.full()
        self.assertTrue((self.t / "evidence/catalog/schema/legal.ttl").exists())
        self.assertTrue((self.t / "evidence/catalog/schema/legal.shapes.ttl").exists())

    def test_locators_include_carried_article(self):
        self.full()
        locs = {c["index"]: c.get("locators") for c in self.chunks() if c["source_id"].endswith("law")}
        self.assertEqual(locs[0], ["제1조", "제2조"])
        self.assertEqual(locs[1], ["제2조"])      # 머리 없이 시작 → 앞 청크의 마지막 조문을 잇는다
        self.assertEqual(locs[2], ["제3조"])
        self.assertFalse(any("locators" in c for c in self.chunks() if c["source_id"].endswith("other")))

    def test_law_name_without_kind_is_caught(self):
        self.full()
        p = self.t / "evidence/catalog/catalog.ttl"
        p.write_text(p.read_text(encoding="utf-8").replace('ecl:lawDocKind "법률" ;', ""), encoding="utf-8")
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("종류", r.stderr)

    def test_unknown_enricher_fails_loudly(self):
        r = self.build("--enricher", "nope")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("알 수 없는 enricher", r.stderr + r.stdout)

    def test_build_is_deterministic_with_enricher(self):
        self.full()
        a, c = self.ttl(), (self.t / "evidence/catalog/chunks.jsonl").read_text(encoding="utf-8")
        self.full()
        self.assertEqual(a, self.ttl())
        self.assertEqual(c, (self.t / "evidence/catalog/chunks.jsonl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
