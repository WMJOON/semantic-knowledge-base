"""수집 기록(seed.retrieval): 리다이렉트 후 최종 URL·상태·형식·응답 해시, 검색 시각은 검색한 경우만, 인자 검증, verify 위반 검출."""
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import convert as _convert  # noqa: E402
import retrieval_meta as _rm  # noqa: E402

VENV_PY = Path(__file__).resolve().parents[2] / "skb-ontology" / ".venv" / "bin" / "python"
PY = str(VENV_PY) if VENV_PY.exists() else sys.executable
HAVE_CAT = subprocess.run([PY, "-c", "import rdflib, pyshacl"], capture_output=True).returncode == 0

BODY = ("<html><head><title>Doc</title></head><body><p>" + "수집 기록 테스트 본문입니다. " * 40 + "</p></body></html>").encode("utf-8")


class H(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/redir":
            self.send_response(302)
            self.send_header("Location", "/doc.html")
            self.end_headers()
        elif self.path == "/doc.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(BODY)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):  # 조용히
        pass


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), H)
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.t = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def collect(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "collect.py"), "--target", str(self.t), "--apply", *args], capture_output=True, text=True)

    def seeds(self):
        p = self.t / "evidence/seeds.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x] if p.exists() else []


class CollectRetrievalTest(Base):
    def test_direct_fetch_records_request_conditions(self):
        r = self.collect("--source", f"{self.base}/doc.html")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.seeds()[0]
        rt = s["retrieval"]
        self.assertEqual(rt["request_url"], f"{self.base}/doc.html")
        self.assertEqual(rt["method"], "GET")
        self.assertEqual(rt["status"], 200)
        self.assertEqual(rt["media_type"], "text/html")
        self.assertEqual(rt["response_sha256"], hashlib.sha256(BODY).hexdigest())
        self.assertIn("retrieved_at", s)               # 내려받은 시각은 최상위(기존)
        self.assertNotIn("searched_at", rt)            # URL 을 직접 지정했으면 검색 시각이 없다

    def test_redirect_records_final_url_but_keeps_requested_uri(self):
        self.collect("--source", f"{self.base}/redir")
        s = self.seeds()[0]
        self.assertEqual(s["uri"], f"{self.base}/redir")
        self.assertEqual(s["retrieval"]["request_url"], f"{self.base}/doc.html")

    def test_search_fields_only_when_given_and_recorded_together(self):
        self.collect("--source", f"{self.base}/doc.html", "--searched-at", "2026-10-06T01:00:00Z", "--search-query", "chunking evaluation")
        rt = self.seeds()[0]["retrieval"]
        self.assertEqual((rt["searched_at"], rt["search_query"]), ("2026-10-06T01:00:00Z", "chunking evaluation"))

    def test_request_params_recorded(self):
        self.collect("--source", f"{self.base}/doc.html", "--request-params", '{"MST": "123", "efYd": "20260101"}')
        self.assertEqual(self.seeds()[0]["retrieval"]["params"], {"MST": "123", "efYd": "20260101"})

    def test_invalid_search_args_are_rejected_before_any_fetch(self):
        for args in (["--searched-at", "2026-10-06T01:00:00Z"], ["--search-query", "q"],
                     ["--searched-at", "yesterday", "--search-query", "q"], ["--request-params", "not-json"], ["--request-params", "[1]"]):
            r = self.collect("--source", f"{self.base}/doc.html", *args)
            self.assertEqual(r.returncode, 2, args)
            self.assertEqual(self.seeds(), [])

    def test_local_intermediate_note_carries_convert_frontmatter(self):
        note = self.t / "n.md"
        note.write_text("---\nsource: https://example.org/paper.pdf\nrequest_url: https://example.org/paper.pdf\nmedia_type: application/pdf\n"
                        "searched_at: 2026-10-06T00:30:00Z\nsearch_query: laya model\nrequest_params: {\"v\": \"2\"}\n---\n\n" + "본문 문장입니다. " * 60, encoding="utf-8")
        r = self.collect("--source", str(note))
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.seeds()[0]
        self.assertEqual(s["uri"], "https://example.org/paper.pdf")
        self.assertEqual(s["retrieval"]["media_type"], "application/pdf")
        self.assertEqual(s["retrieval"]["searched_at"], "2026-10-06T00:30:00Z")
        self.assertEqual(s["retrieval"]["params"], {"v": "2"})
        self.assertNotIn("status", s["retrieval"])      # 원격 응답을 우리가 보지 못한 값은 만들지 않는다

    @unittest.skipUnless(HAVE_CAT, "rdflib/pyshacl 필요")
    def test_catalog_turns_seed_retrieval_into_triples_and_validates(self):
        self.collect("--source", f"{self.base}/doc.html", "--searched-at", "2026-10-06T01:00:00Z", "--search-query", "q1")
        # 검색 시각이 retrieved_at 보다 앞서야 하므로 seed 의 retrieved_at 을 확인용으로 늦춘다(수집 시각은 도구가 방금 기록한 값)
        rows = self.seeds()
        for r in rows:
            r["retrieved_at"] = "2026-10-06T02:00:00Z"
        (self.t / "evidence/seeds.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        b = subprocess.run([PY, str(SCRIPTS / "catalog.py"), "--target", str(self.t), "--apply"], capture_output=True, text=True)
        self.assertEqual(b.returncode, 0, b.stderr)
        ttl = (self.t / "evidence/catalog/catalog.ttl").read_text(encoding="utf-8")
        for needle in ('ec:searchQuery "q1"', "ec:httpStatus 200", 'ec:requestMethod "GET"', 'ec:mediaType "text/html"'):
            self.assertIn(needle, ttl)
        v = subprocess.run([PY, str(SCRIPTS / "catalog_validate.py"), "--target", str(self.t)], capture_output=True, text=True)
        self.assertEqual(v.returncode, 0, v.stderr)


class VerifyRetrievalTest(Base):
    def run_verify(self, retrieval, retrieved_at="2026-10-06T02:00:00Z"):
        self.collect("--source", f"{self.base}/doc.html")
        rows = self.seeds()
        for r in rows:
            r["retrieved_at"] = retrieved_at
            r["retrieval"] = retrieval
        (self.t / "evidence/seeds.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPTS / "verify.py"), "--target", str(self.t), "--shallow"], capture_output=True, text=True)

    def test_good_record_passes(self):
        good = {"request_url": "https://x/y", "method": "GET", "status": 200, "response_sha256": "a" * 64,
                "searched_at": "2026-10-06T01:00:00Z", "search_query": "q"}
        self.assertEqual(self.run_verify(good).returncode, 0)

    def test_searched_without_query_fails(self):
        r = self.run_verify({"searched_at": "2026-10-06T01:00:00Z"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("함께", r.stderr)

    def test_searched_after_retrieved_fails(self):
        r = self.run_verify({"searched_at": "2030-01-01T00:00:00Z", "search_query": "q"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("늦다", r.stderr)

    def test_bad_hash_and_method_fail(self):
        r = self.run_verify({"response_sha256": "zz", "method": "PUT", "status": "200"})
        self.assertEqual(r.returncode, 1)
        for needle in ("response_sha256", "GET|POST", "정수"):
            self.assertIn(needle, r.stderr)


class ConvertFrontmatterTest(unittest.TestCase):
    def test_http_origin_records_request_url_only(self):
        t = _convert._request_frontmatter("https://example.org/a.pdf", "https://example.org/a.pdf", None, None, None)
        self.assertEqual(t, "request_url: https://example.org/a.pdf\n")   # 원격은 docling 이 받아 응답을 보지 못한다

    def test_local_file_records_media_type_and_hash(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.pdf"
            p.write_bytes(b"%PDF-1.4 x")
            t = _convert._request_frontmatter(str(p), str(p), None, None, None)
        self.assertIn("media_type: application/pdf", t)
        self.assertIn("response_sha256: " + hashlib.sha256(b"%PDF-1.4 x").hexdigest(), t)

    def test_render_snapshot_has_no_response_hash(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.html"
            p.write_text("<html></html>", encoding="utf-8")
            t = _convert._request_frontmatter(str(p), "https://example.org/spa", "https://example.org/spa", None, None)
        self.assertIn("request_url: https://example.org/spa", t)
        self.assertIn("media_type: text/html", t)
        self.assertNotIn("response_sha256", t)       # 렌더링 결과는 HTTP 응답이 아니다

    def test_search_and_params_lines(self):
        t = _convert._request_frontmatter("https://e.org/x", "https://e.org/x", None,
                                          {"searched_at": "2026-10-06T00:00:00Z", "search_query": "a b"}, {"k": "v"})
        self.assertIn("searched_at: 2026-10-06T00:00:00Z", t)
        self.assertIn("search_query: a b", t)
        self.assertIn('request_params: {"k": "v"}', t)


class MetaHelpersTest(unittest.TestCase):
    def test_media_type_strips_charset(self):
        self.assertEqual(_rm.media_type("text/html; charset=UTF-8"), "text/html")
        self.assertIsNone(_rm.media_type(""))

    def test_check_search(self):
        self.assertIsNone(_rm.check_search(None, None))
        self.assertIsNone(_rm.check_search("2026-10-06T00:00:00Z", "q"))
        self.assertIsNotNone(_rm.check_search("2026-10-06T00:00:00Z", None))
        self.assertIsNotNone(_rm.check_search("bad", "q"))


if __name__ == "__main__":
    unittest.main()
