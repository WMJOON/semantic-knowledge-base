"""identity propose: 문서가 선언한 발행 주체(계정 없음)도 사람 검토 후보로 올라가고, 결정 없이는 아무것도 승격되지 않는다."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_register as R  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
PY = R.PY


def raw(url: str, publisher: str | None, source: str = "meta:og:site_name") -> str:
    pub = f"publisher: {publisher}\npublisher_source: {source}\npublisher_type: unknown\n" if publisher else "publisher_source: domain-derived\n"
    return (f"---\nsource: {url}\ncollected_at: 2026-10-09T01:02:03Z\ncollected_at_basis: fetch-time\npublished_at: unavailable\n"
            f"published_at_source: none:no-declared-date\n{pub}authors: []\nauthors_source: none:no-declared-author\naccounts: []\n"
            "accounts_source: none:no-platform-account\ndocument_type: unknown\ndocument_type_source: none:not-classified\nconverter: raw-fetch\n---\n\nbody\n")


@unittest.skipUnless(R.HAVE_DEPS, "rdflib/pyshacl 필요")
class PublisherClusterTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.t = Path(self.td.name)
        (self.t / "evidence/raw").mkdir(parents=True)
        docs = [("a.md", "https://example.org/p/1", "Example Press"), ("b.md", "https://example.org/p/2", "example  press"),
                ("c.md", "https://derived.example.net/x", None)]
        with open(self.t / "evidence/seeds.jsonl", "w", encoding="utf-8") as f:
            for i, (name, url, pub) in enumerate(docs, 1):
                (self.t / "evidence/raw" / name).write_text(raw(url, pub), encoding="utf-8")
                f.write(json.dumps(R.seed(i, url)) + "\n")
        for script in ("catalog.py", "register.py"):
            r = subprocess.run([PY, str(SCRIPTS / script), "--target", str(self.t), "--apply"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        self.td.cleanup()

    def identity(self, *a):
        return subprocess.run([PY, str(SCRIPTS / "identity.py"), *a, "--target", str(self.t)], capture_output=True, text=True)

    def queue(self):
        r = self.identity("propose", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        p = self.t / "evidence/identity/review-queue.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]

    def test_declared_publisher_is_clustered_by_normalized_name(self):
        rows = [r for r in self.queue() if r["target_kind"] == "publisher_cluster"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["documents"], 2)
        self.assertEqual(len(rows[0]["targets"]), 2)
        self.assertEqual(rows[0]["total_clusters"], 1)

    def test_domain_derived_publisher_is_never_proposed(self):
        self.assertNotIn("derived.example.net", json.dumps(self.queue()))

    def test_publisher_rows_ignore_max_clusters_cap(self):
        self.identity("propose", "--apply", "--max-clusters", "0")
        rows = [json.loads(x) for x in (self.t / "evidence/identity/review-queue.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["target_kind"] for r in rows], ["publisher_cluster"])

    def test_queue_never_accepts_on_its_own(self):
        self.queue()
        self.assertFalse((self.t / "evidence/identity/identifications.ttl").exists())
        self.assertEqual(self.identity("check").returncode, 0)

    def test_human_decision_resolves_the_cluster_to_an_organization(self):
        row = [r for r in self.queue() if r["target_kind"] == "publisher_cluster"][0]
        d = {"targets": row["targets"], "decision": "accept", "identity": {"kind": "Organization", "slug": "example-press", "label": "Example Press"},
             "methods": ["org-official-listing", "self-declared-bio"], "evidence": ["https://example.org/about"],
             "reviewer": "Won Joon", "decided_at": "2026-10-09T09:00:00Z"}
        (self.t / "evidence/identity/decisions.jsonl").write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")
        r = self.identity("apply", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sa:Organization", (self.t / "evidence/identity/identifications.ttl").read_text(encoding="utf-8"))
        self.assertEqual([x for x in self.queue() if x["target_kind"] == "publisher_cluster"], [])  # 결정된 군집은 다시 제안하지 않는다


if __name__ == "__main__":
    unittest.main()
