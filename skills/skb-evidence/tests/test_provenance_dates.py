"""provenance_dates: 제공자가 선언한 발행일만 추출하고, 없으면 추정하지 않고 사유를 명시한다. (네트워크 불필요)"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import provenance_dates as P  # noqa: E402


class NormalizeTest(unittest.TestCase):
    def test_date_forms(self):
        self.assertEqual(P.normalize("2019/05/29"), "2019-05-29")
        self.assertEqual(P.normalize("2019-5-9"), "2019-05-09")

    def test_datetime_is_converted_to_utc(self):
        self.assertEqual(P.normalize("2026-04-14T09:00:00+09:00"), "2026-04-14T00:00:00Z")
        self.assertEqual(P.normalize("2026-04-14T09:30:00Z"), "2026-04-14T09:30:00Z")

    def test_garbage_is_none(self):
        for bad in (None, "", "yesterday", "2019/13/40", "March 3, 2025"):
            self.assertIsNone(P.normalize(bad), bad)


class ParseHtmlTest(unittest.TestCase):
    def test_jsonld_graph(self):
        html = '<script type="application/ld+json">{"@graph":[{"@type":"Article","datePublished":"2026-04-28T10:00:00Z"}]}</script>'
        self.assertEqual(P.parse_html(html), ("2026-04-28T10:00:00Z", "jsonld:datePublished"))

    def test_meta_article_published_time(self):
        html = '<meta property="article:published_time" content="2026-02-04T08:00:00+00:00">'
        self.assertEqual(P.parse_html(html), ("2026-02-04T08:00:00Z", "meta:article:published_time"))

    def test_scholarly_citation_date(self):
        self.assertEqual(P.parse_html('<meta name="citation_date" content="2019/05/29"/>'),
                         ("2019-05-29", "meta:citation_date"))

    def test_jsonld_wins_over_meta(self):
        html = ('<meta property="article:published_time" content="2020-01-01">'
                '<script type="application/ld+json">{"datePublished":"2021-02-02"}</script>')
        self.assertEqual(P.parse_html(html)[0], "2021-02-02")

    def test_body_text_is_never_used(self):
        html = "<html><body><p>Published March 3, 2025 by someone. Updated 2026-01-01.</p></body></html>"
        self.assertEqual(P.parse_html(html), (None, "none:no-declared-date"))

    def test_unparseable_declared_value_is_none(self):
        self.assertEqual(P.parse_html('<meta property="article:published_time" content="soon">')[0], None)

    def test_broken_html_does_not_raise(self):
        self.assertEqual(P.parse_html("<meta <<< ><script type='application/ld+json'>{bad")[0], None)


class ExtractRoutingTest(unittest.TestCase):
    def test_local_path(self):
        self.assertEqual(P.extract_published("/tmp/x/README.md"), (None, "none:local-file"))

    def test_github_files_have_no_publication_date_and_no_network(self):
        with mock.patch.object(P, "_get", side_effect=AssertionError("network must not be used")):
            for u in ("https://raw.githubusercontent.com/o/r/main/a.py",
                      "https://github.com/o/r/blob/main/docs/a.md",
                      "https://github.com/o/r"):
                self.assertEqual(P.extract_published(u), (None, "none:no-declared-date"), u)

    def test_fetch_error_is_reported_not_swallowed(self):
        with mock.patch.object(P, "_get", return_value=(None, 403)):
            self.assertEqual(P.extract_published("https://example.com/post"), (None, "none:fetch-error-403"))

    def test_given_html_is_used_without_fetching(self):
        html = '<meta property="article:published_time" content="2026-01-02">'
        with mock.patch.object(P, "_get", side_effect=AssertionError("must not fetch")):
            self.assertEqual(P.extract_published("https://example.com/post", html=html),
                             ("2026-01-02", "meta:article:published_time"))

    def test_arxiv_html_and_versioned_urls_are_routed_to_the_abs_page(self):
        # 회귀: arxiv.org/html/<id>[vN] 을 인식하지 못해 15편의 발행일이 빠진 적이 있다.
        page = '<meta name="citation_date" content="2025/02/16"/>'
        for u, aid in (("https://arxiv.org/html/2502.11028v1", "2502.11028"), ("https://arxiv.org/html/2509.23735", "2509.23735"),
                       ("https://arxiv.org/abs/2601.04170v2", "2601.04170")):
            with mock.patch.object(P, "_get", return_value=(page, 200)) as g:
                self.assertEqual(P.extract_published(u), ("2025-02-16", "arxiv:citation_date"), u)
                self.assertIn(f"arxiv.org/abs/{aid}", g.call_args[0][0])

    def test_arxiv_uses_abs_page_citation_date(self):
        page = '<meta name="citation_date" content="2019/05/29"/><meta name="citation_online_date" content="2020/01/01"/>'
        with mock.patch.object(P, "_get", return_value=(page, 200)) as g:
            self.assertEqual(P.extract_published("https://arxiv.org/pdf/1905.03696"), ("2019-05-29", "arxiv:citation_date"))
            self.assertIn("arxiv.org/abs/1905.03696", g.call_args[0][0])


class PublisherTest(unittest.TestCase):
    def test_jsonld_publisher_object(self):
        html = '<script type="application/ld+json">{"@type":"Article","publisher":{"@type":"Organization","name":"Red Hat Developer"}}</script>'
        self.assertEqual(P.parse_publisher(html), ("Red Hat Developer", "jsonld:publisher"))

    def test_og_site_name(self):
        self.assertEqual(P.parse_publisher('<meta property="og:site_name" content="localbench">'), ("localbench", "meta:og:site_name"))

    def test_none_when_nothing_declared(self):
        self.assertEqual(P.parse_publisher("<html><body>by Someone</body></html>"), (None, "none:no-declared-publisher"))

    def test_github_owner_and_raw(self):
        self.assertEqual(P.extract_publisher("https://github.com/jundot/omlx/blob/main/docs/x.md"), ("jundot", "github-owner"))
        self.assertEqual(P.extract_publisher("https://raw.githubusercontent.com/ml-explore/mlx-lm/main/a.py"), ("ml-explore", "github-owner"))

    def test_huggingface_owner_vs_platform_docs(self):
        self.assertEqual(P.extract_publisher("https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/discussions/49"), ("unsloth", "hf-owner"))
        self.assertEqual(P.extract_publisher("https://huggingface.co/docs/hub/ollama"), ("Hugging Face", "platform-host"))
        self.assertEqual(P.extract_publisher("https://huggingface.co/blog/autoround"), ("Hugging Face", "platform-host"))

    def test_arxiv_is_platform(self):
        self.assertEqual(P.extract_publisher("https://arxiv.org/pdf/1905.03696"), ("arXiv", "platform-host"))

    def test_fallback_is_marked_derived_and_keeps_subdomain(self):
        # 한 플랫폼(substack) 안의 서로 다른 발행처를 하나로 뭉개지 않는다. 그리고 '선언'처럼 보이지 않게 표시한다.
        a = P.extract_publisher("https://localbench.substack.com/p/x", html="<html></html>")
        b = P.extract_publisher("https://kaitchup.substack.com/p/y", html="<html></html>")
        self.assertEqual(a, ("localbench.substack.com", "domain-derived"))
        self.assertNotEqual(a[0], b[0])

    def test_declared_publisher_beats_domain(self):
        html = '<meta property="og:site_name" content="LocalBench">'
        self.assertEqual(P.extract_publisher("https://localbench.substack.com/p/x", html=html), ("LocalBench", "meta:og:site_name"))

    def test_local_file(self):
        self.assertEqual(P.extract_publisher("/tmp/x/README.md"), ("local", "local-file"))

    def test_extract_all_fetches_html_once_for_generic_pages(self):
        page = ('<meta property="article:published_time" content="2026-01-02"><meta property="og:site_name" content="Site">')
        with mock.patch.object(P, "_get", return_value=(page, 200)) as g:
            r = P.extract_all("https://example.com/post")
        self.assertEqual(g.call_count, 1)
        self.assertEqual((r["published_at"], r["publisher"], r["publisher_source"]), ("2026-01-02", "Site", "meta:og:site_name"))

    def test_extract_all_reports_fetch_error_and_still_gives_host(self):
        with mock.patch.object(P, "_get", return_value=(None, 403)):
            r = P.extract_all("https://developers.redhat.com/articles/x")
        self.assertEqual((r["published_at"], r["published_at_source"]), (None, "none:fetch-error-403"))
        self.assertEqual((r["publisher"], r["publisher_source"]), ("developers.redhat.com", "domain-derived"))


class AuthorTest(unittest.TestCase):
    def test_jsonld_author_person_with_declared_affiliation(self):
        html = '<script type="application/ld+json">{"author":{"@type":"Person","name":"Jane Doe","affiliation":{"@type":"Organization","name":"Acme Lab"}}}</script>'
        self.assertEqual(P.parse_authors(html), ([{"name": "Jane Doe", "type": "Person", "affiliation": "Acme Lab", "account": None}], "jsonld:author"))

    def test_jsonld_author_list_and_plain_string(self):
        html = '<script type="application/ld+json">{"author":["Ann", {"@type":"Organization","name":"Some Org"}]}</script>'
        out, src = P.parse_authors(html)
        self.assertEqual(src, "jsonld:author")
        self.assertEqual([(a["name"], a["type"]) for a in out], [("Ann", None), ("Some Org", "Organization")])

    def test_citation_author_multi_values_keep_order(self):
        html = '<meta name="citation_author" content="Dong, Zhen"><meta name="citation_author" content="Yao, Zhewei">'
        out, src = P.parse_authors(html)
        self.assertEqual((src, [a["name"] for a in out]), ("meta:citation_author", ["Dong, Zhen", "Yao, Zhewei"]))

    def test_affiliation_kept_only_when_counts_align(self):
        ok = '<meta name="citation_author" content="A"><meta name="citation_author_institution" content="X"><meta name="citation_author" content="B"><meta name="citation_author_institution" content="Y">'
        self.assertEqual([a["affiliation"] for a in P.parse_authors(ok)[0]], ["X", "Y"])
        skew = '<meta name="citation_author" content="A"><meta name="citation_author" content="B"><meta name="citation_author_institution" content="X">'
        self.assertEqual([a["affiliation"] for a in P.parse_authors(skew)[0]], [None, None])      # 어긋나면 소속을 추측해 붙이지 않는다

    def test_article_author_profile_url_is_not_an_author_name(self):
        self.assertEqual(P.parse_authors('<meta property="article:author" content="https://example.com/people/jane">'), ([], "none:no-declared-author"))

    def test_byline_in_body_text_is_never_used(self):
        self.assertEqual(P.parse_authors("<html><body><p>By Sam Altman, OpenAI</p></body></html>"), ([], "none:no-declared-author"))

    def test_github_files_have_no_author_and_no_network(self):
        with mock.patch.object(P, "_github_json", side_effect=AssertionError("network must not be used")):
            self.assertEqual(P.extract_authors("https://github.com/o/r/blob/main/a.md", None), ([], "none:no-declared-author"))

    def test_github_discussion_author_is_the_declared_user_with_type(self):
        with mock.patch.object(P, "_github_json", return_value={"user": {"login": "ddh0", "type": "User"}}):
            out, src = P.extract_authors("https://github.com/o/r/discussions/12741", None)
        self.assertEqual((src, out), ("github-api:user", [{"name": "ddh0", "type": "Person", "affiliation": None, "account": "ddh0"}]))


class PublisherTypeTest(unittest.TestCase):
    def test_github_owner_type_comes_from_api(self):
        P._github_owner_type.cache_clear()
        with mock.patch.object(P, "_github_json", return_value={"type": "Organization"}):
            self.assertEqual(P.extract_publisher_type("https://github.com/unslothai/unsloth", None, "github-owner"), ("Organization", "github-api:type"))

    def test_github_person(self):
        P._github_owner_type.cache_clear()
        with mock.patch.object(P, "_github_json", return_value={"type": "User"}):
            self.assertEqual(P.extract_publisher_type("https://github.com/jundot/omlx", None, "github-owner"), ("Person", "github-api:type"))

    def test_lookup_failure_is_unknown_with_reason_not_guessed(self):
        P._github_owner_type.cache_clear()
        with mock.patch.object(P, "_github_json", return_value=None):
            self.assertEqual(P.extract_publisher_type("https://github.com/x/y", None, "github-owner"), ("unknown", "none:fetch-error-github-api"))

    def test_jsonld_publisher_type_declared(self):
        html = '<script type="application/ld+json">{"publisher":{"@type":"Organization","name":"Red Hat"}}</script>'
        self.assertEqual(P.extract_publisher_type("https://x.com/a", html, "jsonld:publisher"), ("Organization", "jsonld:publisher.@type"))

    def test_platform_and_domain_derived_are_not_guessed(self):
        # arXiv 나 호스트명은 '조직처럼 보여도' 선언되지 않았으므로 unknown 이다.
        for src in ("platform-host", "domain-derived", "meta:og:site_name"):
            self.assertEqual(P.extract_publisher_type("https://x.com/a", "<html></html>", src), ("unknown", "none:not-declared"), src)


class ExtractAllArxivTest(unittest.TestCase):
    def test_arxiv_abstract_page_is_fetched_once_for_date_and_authors(self):
        page = '<meta name="citation_date" content="2019/05/29"/><meta name="citation_author" content="Dong, Zhen"/>'
        with mock.patch.object(P, "_get", return_value=(page, 200)) as g:
            r = P.extract_all("https://arxiv.org/pdf/1905.03696")
        self.assertEqual(g.call_count, 1)
        self.assertEqual((r["published_at"], r["authors_source"], [a["name"] for a in r["authors"]]), ("2019-05-29", "meta:citation_author", ["Dong, Zhen"]))
        self.assertEqual((r["publisher"], r["publisher_type"]), ("arXiv", "unknown"))


def _clear():
    for fn in (P._github_json, P.github_account, P.hf_account, P._hf_json, P._github_owner_type, P._hf_owner_type):
        fn.cache_clear()


class AccountFactsTest(unittest.TestCase):
    def setUp(self):
        _clear()

    def test_github_org_account_takes_verified_from_orgs_endpoint(self):
        def gj(path):
            return {"users/unslothai": {"login": "unslothai", "id": 150920049, "type": "Organization", "created_at": "2023-12-01T00:00:00Z",
                                        "name": "Unsloth AI", "blog": "unsloth.ai", "twitter_username": "unslothai",
                                        "email": "secret-address", "location": "SF", "followers": 999},
                    "orgs/unslothai": {"is_verified": True}}.get(path)
        with mock.patch.object(P, "_github_json", side_effect=gj):
            a = P.github_account("unslothai")
        self.assertEqual((a["id"], a["type"], a["verified"], a["links"], a["twitter"]), (150920049, "Organization", True, ["https://unsloth.ai"], "unslothai"))
        for forbidden in ("email", "location", "followers"):                       # 개인정보 최소화
            self.assertNotIn(forbidden, a)

    def test_github_user_verified_is_null_not_false(self):
        with mock.patch.object(P, "_github_json", return_value={"login": "ddh0", "id": 7, "type": "User"}):
            a = P.github_account("ddh0")
        self.assertEqual((a["type"], a["verified"]), ("Person", None))        # 플랫폼이 선언하지 않은 값은 False 가 아니라 null

    def test_bio_is_truncated(self):
        with mock.patch.object(P, "_github_json", return_value={"login": "x", "id": 1, "type": "User", "bio": "a" * 999}):
            self.assertEqual(len(P.github_account("x")["declared_bio"]), 300)

    def test_hf_org_and_user_and_missing(self):
        def hj(path):
            return {"organizations/unsloth/overview": {"_id": "o1", "name": "unsloth", "fullname": "Unsloth AI", "isVerified": True},
                    "users/bartowski/overview": {"_id": "u1", "user": "bartowski", "fullname": "Bartowski", "details": "Senior Machine Learning Engineer at RedHat",
                                                 "createdAt": "2023-04-11T14:41:14.000Z", "numFollowers": 15725}}.get(path)
        with mock.patch.object(P, "_hf_json", side_effect=hj):
            o, u, none = P.hf_account("unsloth"), P.hf_account("bartowski"), P.hf_account("nobody")
        self.assertEqual((o["type"], o["verified"], o["id"]), ("Organization", True, "o1"))
        self.assertEqual((u["type"], u["declared_bio"], u["created_at"]), ("Person", "Senior Machine Learning Engineer at RedHat", "2023-04-11T14:41:14Z"))
        self.assertNotIn("numFollowers", u)
        self.assertIsNone(none)

    def test_hf_discussion_author_is_third_party_with_platform_declared_membership(self):
        d = {"author": {"_id": "u9", "name": "x0me", "fullname": "Pascal", "type": "user"}, "org": {"name": "unsloth"},
             "events": [{"author": {"name": "x0me", "isOrgMember": False}}]}
        with mock.patch.object(P, "_hf_json", return_value=d):
            a = P.hf_discussion_author("https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/discussions/49")
        self.assertEqual((a["handle"], a["type"], a["is_member_of_host_org"]), ("x0me", "Person", False))

    def test_publisher_and_author_accounts_are_kept_separate(self):
        # 같은 문서의 발행 주체(저장소 소유자)와 저자(토론 작성자)는 다른 계정, 다른 role 이다
        def hj(path):
            if path.endswith("/discussions/49"):
                return {"author": {"_id": "u9", "name": "x0me", "type": "user"}, "events": [{"author": {"isOrgMember": False}}]}
            return {"organizations/unsloth/overview": {"_id": "o1", "name": "unsloth", "isVerified": True}}.get(path)
        with mock.patch.object(P, "_hf_json", side_effect=hj):
            accts, src = P.extract_accounts("https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/discussions/49", [], "hf-owner")
        self.assertEqual({(a["role"], a["handle"]) for a in accts}, {("publisher", "unsloth"), ("author", "x0me")})
        self.assertEqual(src, "hf-api")

    def test_no_accounts_for_domain_derived_publisher(self):
        self.assertEqual(P.extract_accounts("https://smcleod.net/2026/04/x", [], "domain-derived"), ([], "none:no-platform-account"))

    def test_github_publisher_and_issue_author(self):
        def gj(path):
            return {"users/ggml-org": {"login": "ggml-org", "id": 1, "type": "Organization"}, "orgs/ggml-org": {"is_verified": False},
                    "users/ddh0": {"login": "ddh0", "id": 2, "type": "User"}}.get(path)
        authors = [{"name": "ddh0", "type": "Person", "affiliation": None, "account": "ddh0"}]
        with mock.patch.object(P, "_github_json", side_effect=gj):
            accts, _ = P.extract_accounts("https://github.com/ggml-org/llama.cpp/discussions/12741", authors, "github-owner")
        self.assertEqual({(a["role"], a["handle"], a["verified"]) for a in accts}, {("publisher", "ggml-org", False), ("author", "ddh0", None)})


class DocumentTypeTest(unittest.TestCase):
    def test_scholarly_jsonld(self):
        html = '<script type="application/ld+json">{"@type":"ScholarlyArticle","name":"x"}</script>'
        self.assertEqual(P.classify_document("https://example.org/a", html), ("paper", "jsonld:@type"))

    def test_citation_meta_needs_a_scholarly_companion(self):
        ok = '<meta name="citation_title" content="T"><meta name="citation_doi" content="10.1/x">'
        self.assertEqual(P.classify_document("https://example.org/a", ok), ("paper", "meta:citation_*"))
        alone = '<meta name="citation_title" content="T">'                        # 제목만으로는 논문이라고 단정하지 않는다
        self.assertEqual(P.classify_document("https://example.org/a", alone), ("unknown", "none:not-classified"))

    def test_preprint_servers_are_papers_by_platform(self):
        for u in ("https://arxiv.org/pdf/1905.03696", "https://www.medrxiv.org/content/10.1101/2025.08.23.25334280v1"):
            self.assertEqual(P.classify_document(u, None), ("paper", "platform-host"), u)

    def test_blog_and_docs_and_repo_are_unknown_not_guessed(self):
        blog = '<meta property="og:type" content="article"><p>Abstract: we show ...</p>'
        for u, h in (("https://smcleod.net/2026/04/x", blog), ("https://docs.vllm.ai/en/latest/", None), ("https://github.com/o/r", None)):
            self.assertEqual(P.classify_document(u, h), ("unknown", "none:not-classified"), u)

    def test_local_file_unknown(self):
        self.assertEqual(P.classify_document("/tmp/x/paper.md", None), ("unknown", "none:not-classified"))

    def test_extract_all_marks_arxiv_as_paper(self):
        page = '<meta name="citation_date" content="2019/05/29"/><meta name="citation_author" content="Dong, Zhen"/><meta name="citation_title" content="HAWQ"/><meta name="citation_arxiv_id" content="1905.03696"/>'
        with mock.patch.object(P, "_get", return_value=(page, 200)):
            r = P.extract_all("https://arxiv.org/pdf/1905.03696")
        self.assertEqual((r["document_type"], r["document_type_source"]), ("paper", "meta:citation_*"))


class HuggingFacePageAuthorTest(unittest.TestCase):
    def setUp(self):
        _clear()

    def test_hf_model_card_page_html_is_fetched_for_authors_but_discussion_uses_api(self):
        page = '<meta name="author" content="Jane Doe">'
        with mock.patch.object(P, "_get", return_value=(page, 200)) as g, mock.patch.object(P, "_hf_json", return_value=None):
            r = P.extract_all("https://huggingface.co/blog/autoround")
        self.assertGreaterEqual(g.call_count, 1)                                    # 회귀: 예전에는 HTML 을 받지 않아 none:no-html 이었다
        self.assertEqual((r["authors_source"], [a["name"] for a in r["authors"]]), ("meta:author", ["Jane Doe"]))
        def api_only(url, *a, **k):                                                   # 토론은 API 주소만 호출해야 한다(HTML 페이지 금지)
            assert "/api/" in url, f"discussion must use the API, not the HTML page: {url}"
            return None, 404

        with mock.patch.object(P, "_get", side_effect=api_only), mock.patch.object(
                P, "_hf_json", return_value={"author": {"_id": "u", "name": "x0me", "type": "user"}, "events": [{"author": {}}]}):
            r = P.extract_all("https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/discussions/49", html="<html></html>")
        self.assertEqual(r["authors_source"], "hf-api:discussion.author")


if __name__ == "__main__":
    unittest.main()
