"""verify._raw_date_failures: 모든 evidence/raw 원문은 수집일(collected_at)을 반드시 표기해야 한다."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import verify as V  # noqa: E402

AUTHORS = '[{"name": "Jane Doe", "type": "Person", "affiliation": null, "account": null}]'
GOOD = (
    "---\n"
    "source: https://example.com/a\n"
    "collected_at: 2026-09-30T01:02:03Z\n"
    "collected_at_basis: fetch-time\n"
    "published_at: 2026-04-14\n"
    "published_at_source: jsonld:datePublished\n"
    "publisher: localbench\n"
    "publisher_source: jsonld:publisher\n"
    "publisher_type: Organization\n"
    "publisher_type_source: jsonld:publisher.@type\n"
    "authors: " + AUTHORS + "\n"
    "authors_source: jsonld:author\n"
    "accounts: []\n"
    "accounts_source: none:no-platform-account\n"
    "document_type: paper\n"
    "document_type_source: meta:citation_*\n"
    "converter: docling\n"
    "---\n\nbody\n"
)


class RawDateTest(unittest.TestCase):
    def check(self, name_to_text):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            for n, t in name_to_text.items():
                (d / n).write_text(t, encoding="utf-8")
            return V._raw_date_failures(d)

    def test_complete_document_passes(self):
        self.assertEqual(self.check({"a.md": GOOD}), [])

    def test_unavailable_publication_date_with_reason_passes(self):
        t = GOOD.replace("published_at: 2026-04-14", "published_at: unavailable").replace("jsonld:datePublished", "none:no-declared-date")
        self.assertEqual(self.check({"a.md": t}), [])

    def test_missing_collected_at_fails(self):
        t = GOOD.replace("collected_at: 2026-09-30T01:02:03Z\n", "")
        self.assertTrue(any("collected_at" in f for f in self.check({"a.md": t})))

    def test_legacy_document_without_any_date_fails(self):
        legacy = "---\nsource: https://example.com/a\nconverter: docling\ncollected_via: source-note-primary-fetch\n---\n\nbody\n"
        fails = self.check({"legacy.md": legacy})
        self.assertTrue(any("collected_at" in f for f in fails))
        self.assertTrue(any("published_at" in f for f in fails))

    def test_date_only_collected_at_is_rejected(self):
        # 수집일은 시각(UTC ISO)까지 기록한다
        t = GOOD.replace("2026-09-30T01:02:03Z", "2026-09-30")
        self.assertTrue(any("collected_at" in f for f in self.check({"a.md": t})))

    def test_publication_date_without_source_fails(self):
        t = GOOD.replace("published_at_source: jsonld:datePublished\n", "")
        self.assertTrue(any("published_at_source" in f for f in self.check({"a.md": t})))

    def test_invented_publication_date_format_fails(self):
        t = GOOD.replace("published_at: 2026-04-14", "published_at: April 2026")
        self.assertTrue(any("published_at" in f for f in self.check({"a.md": t})))

    def test_missing_publisher_fails(self):
        t = GOOD.replace("publisher: localbench\n", "")
        self.assertTrue(any("publisher(발행 주체)" in f for f in self.check({"a.md": t})))

    def test_publisher_without_source_fails(self):
        t = GOOD.replace("publisher_source: jsonld:publisher\n", "")
        self.assertTrue(any("publisher_source" in f for f in self.check({"a.md": t})))

    def test_empty_authors_list_with_reason_passes(self):
        t = GOOD.replace("authors: " + AUTHORS, "authors: []").replace("jsonld:author", "none:no-declared-author")
        self.assertEqual(self.check({"a.md": t}), [])

    def test_missing_or_malformed_authors_fails(self):
        for bad in (GOOD.replace("authors: " + AUTHORS + "\n", ""),
                    GOOD.replace(AUTHORS, "Jane Doe"),
                    GOOD.replace(AUTHORS, '[{"type": "Person"}]')):
            self.assertTrue(any("authors" in f for f in self.check({"a.md": bad})), bad[:80])

    def test_authors_without_source_fails(self):
        self.assertTrue(any("authors_source" in f for f in self.check({"a.md": GOOD.replace("authors_source: jsonld:author\n", "")})))

    def test_publisher_type_must_be_one_of_three(self):
        self.assertTrue(any("publisher_type" in f for f in self.check({"a.md": GOOD.replace("publisher_type: Organization", "publisher_type: Company")})))
        self.assertTrue(any("publisher_type" in f for f in self.check({"a.md": GOOD.replace("publisher_type: Organization\n", "")})))

    def test_publisher_type_without_source_fails(self):
        self.assertTrue(any("publisher_type_source" in f for f in self.check({"a.md": GOOD.replace("publisher_type_source: jsonld:publisher.@type\n", "")})))

    def test_accounts_with_stable_id_pass(self):
        acct = '[{"platform": "github", "handle": "unslothai", "id": 150920049, "role": "publisher", "verified": true}]'
        self.assertEqual(self.check({"a.md": GOOD.replace("accounts: []", "accounts: " + acct)}), [])

    def test_account_without_stable_id_or_valid_role_fails(self):
        for bad in ('[{"platform": "github", "handle": "x", "role": "publisher"}]',                       # 불변 id 없음
                    '[{"platform": "github", "handle": "x", "id": 1, "role": "owner"}]',                  # 허용되지 않은 role
                    '"not-a-list"'):
            self.assertTrue(any("accounts" in f for f in self.check({"a.md": GOOD.replace("accounts: []", "accounts: " + bad)})), bad)

    def test_missing_accounts_or_source_fails(self):
        self.assertTrue(any("accounts" in f for f in self.check({"a.md": GOOD.replace("accounts: []\n", "")})))
        self.assertTrue(any("accounts_source" in f for f in self.check({"a.md": GOOD.replace("accounts_source: none:no-platform-account\n", "")})))

    def test_document_type_must_be_paper_or_unknown_with_source(self):
        self.assertEqual(self.check({"a.md": GOOD.replace("document_type: paper", "document_type: unknown").replace("meta:citation_*", "none:not-classified")}), [])
        self.assertTrue(any("document_type" in f for f in self.check({"a.md": GOOD.replace("document_type: paper", "document_type: blog")})))
        self.assertTrue(any("document_type" in f for f in self.check({"a.md": GOOD.replace("document_type: paper\n", "")})))
        self.assertTrue(any("document_type_source" in f for f in self.check({"a.md": GOOD.replace("document_type_source: meta:citation_*\n", "")})))

    def test_no_frontmatter_fails(self):
        self.assertTrue(self.check({"a.md": "just text"}))


if __name__ == "__main__":
    unittest.main()
