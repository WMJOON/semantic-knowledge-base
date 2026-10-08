"""register: 카탈로그 → AgentMention·Account 등록. 신원 승격 없음, lexical·SHACL 게이트, 멱등성·충돌."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ONT = Path(__file__).resolve().parents[2] / "skb-ontology"
VENV_PY = ONT / ".venv" / "bin" / "python"
PY = str(VENV_PY) if VENV_PY.exists() else sys.executable
HAVE_DEPS = subprocess.run([PY, "-c", "import rdflib, pyshacl"], capture_output=True).returncode == 0  # skb-ontology/requirements.txt

RAW = (
    "---\nsource: https://github.com/acme/tool\ncollected_at: 2026-09-30T01:02:03Z\ncollected_at_basis: fetch-time\n"
    "published_at: 2026-04-14\npublished_at_source: github-api:created_at\npublisher: acme\npublisher_source: github-owner\n"
    "publisher_type: Organization\npublisher_type_source: github-api:owner.type\n"
    'authors: [{"name": "Jane Doe", "type": "Person", "affiliation": "Acme Labs", "account": "jdoe"}, {"name": "Kim Lee", "type": null, "affiliation": null, "account": null}]\n'
    "authors_source: github-api:contributors\n"
    'accounts: [{"platform": "github", "handle": "acme", "id": 1234, "type": "Organization", "role": "publisher"}, '
    '{"platform": "github", "handle": "jdoe", "id": 99, "type": "Person", "role": "author"}]\n'
    "accounts_source: github-api\ndocument_type: unknown\ndocument_type_source: none:not-classified\nconverter: raw-fetch\n---\n\nbody one\n"
)


def seed(i, uri):
    return {"id": f"evidence:seed:s{i}_0000", "kind": "url", "uri": uri, "retrieved_at": "2026-09-30T01:02:03Z",
            "content_hash": "sha256:" + "a" * 64, "title": f"T{i}", "chunk": {"index": 0, "total": 1, "char_start": 0, "char_end": 500},
            "claims": [], "status": "collected", "md_path": f"evidence/md/s{i}_0000.md", "tool_version": "skb-evidence/1.2.0"}


@unittest.skipUnless(HAVE_DEPS, "rdflib/pyshacl 필요")
class RegisterTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.t = Path(self.td.name)
        (self.t / "evidence/raw").mkdir(parents=True)
        self.write_raw("a.md", RAW)
        with open(self.t / "evidence/seeds.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps(seed(1, "https://github.com/acme/tool")) + "\n")
        self.catalog()

    def tearDown(self):
        self.td.cleanup()

    def write_raw(self, name, text):
        (self.t / "evidence/raw" / name).write_text(text, encoding="utf-8")

    def catalog(self):
        r = subprocess.run([PY, str(SCRIPTS / "catalog.py"), "--target", str(self.t), "--apply"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def register(self, *extra):
        r = subprocess.run([PY, str(SCRIPTS / "register.py"), "--target", str(self.t), *extra], capture_output=True, text=True)
        try:
            res = json.loads(r.stdout)["results"]
        except ValueError:
            res = []
        return r.returncode, res, r

    def files(self):
        d = self.t / "evidence/registrations"
        return sorted(d.glob("*.ttl")) if d.exists() else []

    def ttl(self):
        return self.files()[0].read_text(encoding="utf-8")

    def test_dry_run_passes_and_writes_nothing(self):
        rc, res, _ = self.register()
        self.assertEqual((rc, res[0]["status"]), (0, "dry_run_passed"))
        self.assertEqual(self.files(), [])

    def test_registers_mentions_and_accounts(self):
        rc, res, r = self.register("--apply")
        self.assertEqual((rc, res[0]["status"]), (0, "registered"), r.stderr)
        self.assertEqual((res[0]["mentions"], res[0]["accounts"]), (3, 2))
        t = self.ttl()
        self.assertIn('sa:declaredName "Jane Doe"', t)
        self.assertIn('sa:declaredType "Person"', t)
        self.assertIn('sa:declaredAffiliation "Acme Labs"', t)
        self.assertIn("sa:observedAccount", t)
        self.assertIn("concept:source-agent-role-publisher", t)

    def test_unspecified_author_type_is_unknown(self):
        self.register("--apply")
        self.assertIn('sa:declaredName "Kim Lee"', self.ttl())
        self.assertIn('sa:declaredType "unknown"', self.ttl())

    def test_no_identity_is_promoted(self):
        self.register("--apply")
        t = self.ttl()
        for banned in ("sa:Person", "sa:MentionIdentification", "sa:TrustFactorAssessment", "sa:Organization", "sa:identificationStatus"):
            self.assertNotIn(banned, t)

    def test_domain_derived_publisher_is_not_a_mention(self):
        self.write_raw("a.md", RAW.replace("publisher_source: github-owner", "publisher_source: domain-derived"))
        self.catalog()
        _, res, _ = self.register("--apply")
        self.assertEqual(res[0]["mentions"], 2)
        self.assertTrue(any("domain-derived" in n for n in res[0]["notes"]))

    def test_authorless_document_registers_without_mentions(self):
        raw = RAW.replace(RAW[RAW.index("authors: ["):RAW.index("authors_source")], "authors: []\n").replace(
            "publisher: acme", "publisher: acme").replace("publisher_source: github-owner", "publisher_source: domain-derived")
        self.write_raw("a.md", raw)
        self.catalog()
        rc, res, _ = self.register("--apply")
        self.assertEqual((rc, res[0]["mentions"]), (0, 0))

    def test_replacement_char_blocks_registration(self):
        self.write_raw("a.md", RAW.replace("Kim Lee", "Kim L�e"))
        self.catalog()
        rc, res, _ = self.register("--apply")
        self.assertEqual((rc, res[0]["status"]), (2, "lexical_error"))
        self.assertEqual(self.files(), [])

    def test_irregular_whitespace_warns_but_registers(self):
        self.write_raw("a.md", RAW.replace("Kim Lee", "Kim  Lee"))
        self.catalog()
        rc, res, _ = self.register("--apply")
        self.assertEqual((rc, res[0]["status"]), (0, "registered"))
        self.assertTrue(any(f["code"] == "irregular-whitespace" for f in res[0]["lexical"]))

    def test_second_apply_is_already_registered(self):
        self.register("--apply")
        before = self.ttl()
        rc, res, _ = self.register("--apply")
        self.assertEqual((rc, res[0]["status"]), (0, "already_registered"))
        self.assertEqual(before, self.ttl())

    def test_changed_snapshot_conflicts_and_preserves_existing(self):
        self.register("--apply")
        before = self.ttl()
        self.write_raw("a.md", RAW.replace("body one", "body two"))
        rc, res, _ = self.register("--apply")
        self.assertEqual((rc, res[0]["status"]), (2, "conflict"))
        self.assertEqual(before, self.ttl())

    def test_registration_is_deterministic(self):
        self.register("--apply")
        first = self.ttl()
        shutil.rmtree(self.t / "evidence/registrations")
        self.register("--apply")
        self.assertEqual(first, self.ttl())

    def check(self):
        return subprocess.run([PY, str(SCRIPTS / "register.py"), "--target", str(self.t), "--check"], capture_output=True, text=True)

    def test_written_files_pass_check(self):
        self.register("--apply")
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"checked": 1', r.stdout)

    def test_hand_edited_violation_is_caught_by_check(self):
        self.register("--apply")
        f = self.files()[0]
        f.write_text(f.read_text(encoding="utf-8").replace('sa:declaredType "Person"', 'sa:declaredType "Robot"'), encoding="utf-8")
        r = self.check()
        self.assertEqual(r.returncode, 2)
        self.assertIn("declaredType", r.stderr)

    def test_missing_catalog_fails(self):
        shutil.rmtree(self.t / "evidence/catalog")
        rc, _, r = self.register()
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
