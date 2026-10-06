"""verify_quotes.check_claims: quote 가 원문에 글자 그대로 한 번 있는지, inference basis 가 fact 인지."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import verify_quotes as Q  # noqa: E402

Q1 = "The quick brown fox jumps over the lazy dog near the riverbank today."
RAW = f"intro text\n{Q1}\nOther sentence that appears twice in this document for testing.\nOther sentence that appears twice in this document for testing.\n"


class QuoteTest(unittest.TestCase):
    def check(self, claims, report=None):
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            (t / "evidence/raw").mkdir(parents=True)
            (t / "evidence/raw/a.md").write_text(RAW, encoding="utf-8")
            return Q.check_claims(claims, t, report_text=report)

    def fact(self, cid="T1-01", quote=Q1, raw="evidence/raw/a.md"):
        return {"id": cid, "type": "fact", "raw": raw, "quote": quote}

    def test_exact_unique_quote_passes(self):
        self.assertEqual(self.check([self.fact()])["issues"], [])

    def test_altered_quote_fails(self):
        r = self.check([self.fact(quote=Q1.replace("quick", "slow"))])
        self.assertTrue(any("0번" in i for i in r["issues"]))

    def test_repeated_quote_fails(self):
        q = "Other sentence that appears twice in this document for testing."
        r = self.check([self.fact(quote=q)])
        self.assertTrue(any("2번" in i for i in r["issues"]))

    def test_missing_raw_fails(self):
        r = self.check([self.fact(raw="evidence/raw/none.md")])
        self.assertTrue(any("raw 파일" in i for i in r["issues"]))

    def test_short_quote_fails(self):
        r = self.check([self.fact(quote="intro text")])
        self.assertTrue(any("길이" in i for i in r["issues"]))

    def test_duplicate_id_fails(self):
        r = self.check([self.fact(), self.fact()])
        self.assertTrue(any("id 중복" in i for i in r["issues"]))

    def test_inference_basis_must_be_fact(self):
        inf = {"id": "T1-02", "type": "inference", "quote": "", "basis": ["T1-99"]}
        r = self.check([self.fact(), inf])
        self.assertTrue(any("fact id 가 아님" in i for i in r["issues"]))

    def test_valid_inference_passes(self):
        inf = {"id": "T1-02", "type": "inference", "quote": "", "basis": ["T1-01"]}
        self.assertEqual(self.check([self.fact(), inf])["issues"], [])

    def test_report_citation_not_in_claims_fails(self):
        r = self.check([self.fact()], report="주장 [T1-01] 그리고 [T1-07].")
        self.assertTrue(any("claims 에 없음" in i for i in r["issues"]))

    def test_uncited_fact_is_counted_not_failed(self):
        r = self.check([self.fact()], report="인용 없음")
        self.assertEqual((r["issues"], r["uncited_facts"]), ([], 1))


if __name__ == "__main__":
    unittest.main()
