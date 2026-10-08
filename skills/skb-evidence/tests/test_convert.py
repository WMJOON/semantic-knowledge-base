"""convert.py 회귀 테스트 (네트워크·docling 불필요).

배경: docling 기본 image-export-mode(embedded)가 PDF 그림을 data URI(base64)로 본문에 넣고,
청킹이 이를 잘라 seed 의 80% 를 이미지 조각으로 채웠다(2026-09-30 mixed-precision 리서치).
"""
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import convert as C  # noqa: E402

_B64 = "iVBORw0KGgo" + "A" * 4000


class CleanMarkdownTest(unittest.TestCase):
    def test_data_uri_image_is_replaced_and_text_is_kept(self):
        md = f"## Title\n\nbefore\n\n![Image](data:image/png;base64,{_B64})\n\nafter\n"
        out = C._clean_markdown(md)
        self.assertNotIn("base64", out)
        self.assertIsNone(re.search(r"[A-Za-z0-9+/=]{300,}", out))
        self.assertIn("[image omitted]", out)
        self.assertIn("before", out)
        self.assertIn("after", out)

    def test_multiline_wrapped_base64_is_removed(self):
        wrapped = "\n".join(_B64[i:i + 76] for i in range(0, len(_B64), 76))
        out = C._clean_markdown(f"x\n![a](data:image/jpeg;base64,{wrapped})\ny\n")
        self.assertNotIn("iVBOR", out)

    def test_plain_links_and_images_untouched(self):
        md = "![fig](https://example.com/a.png) and [t](https://example.com)\n"
        self.assertEqual(C._clean_markdown(md).strip(), md.strip())


class GithubFallbackTest(unittest.TestCase):
    def _fake(self, body):
        resp = mock.Mock()
        resp.read.return_value = body.encode("utf-8")
        return mock.patch("urllib.request.urlopen", return_value=resp)

    def test_blob_md_maps_to_raw_and_returns_text(self):
        with self._fake("# doc\n") as m:
            got = C._github_text_fallback("https://github.com/o/r/blob/main/docs/a.md")
        self.assertEqual(got, "# doc\n")
        self.assertEqual(m.call_args[0][0].full_url, "https://raw.githubusercontent.com/o/r/main/docs/a.md")

    def test_code_is_fenced(self):
        with self._fake("print(1)\n"):
            got = C._github_text_fallback("https://raw.githubusercontent.com/o/r/main/x.py")
        self.assertTrue(got.startswith("```py\n"))
        self.assertTrue(got.rstrip().endswith("```"))

    def test_non_github_and_binary_return_none(self):
        self.assertIsNone(C._github_text_fallback("https://example.com/a.md"))
        self.assertIsNone(C._github_text_fallback("https://github.com/o/r/blob/main/a.png"))


if __name__ == "__main__":
    unittest.main()


class MarkdownPassthroughTest(unittest.TestCase):
    """이미 마크다운인 원문은 docling 을 거치지 않는다(docling 은 중첩 목록의 문장을 떨어뜨린다)."""

    NESTED = ("##### 제1조 (정의)\n\n**①** 다음 각 호의 정의를 따른다.\n\n  1\\. 갑 정의\n\n    가\\. 갑의 첫째 목 문장\n\n    나\\. 갑의 둘째 목 문장\n\n  2\\. 을 정의\n")

    def test_local_markdown_is_used_verbatim_without_docling(self):
        import convert as C
        import tempfile
        from pathlib import Path
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "doc.md"
            src.write_text(self.NESTED, encoding="utf-8")
            raw_dir = Path(td) / "raw"
            with mock.patch.object(C.shutil, "which", return_value=None):   # docling 이 없어도 변환된다
                rec = C.convert(str(src), raw_dir)
            self.assertEqual(rec["status"], "ok", rec["error"])
            text = (Path(td) / rec["md"] if Path(rec["md"]).is_absolute() else raw_dir / Path(rec["md"]).name).read_text(encoding="utf-8")
        for needle in ("갑의 첫째 목 문장", "갑의 둘째 목 문장", "을 정의"):
            self.assertIn(needle, text)          # 중첩 목록 문장이 남는다
        self.assertIn("converter: passthrough", text)

    def test_github_raw_markdown_url_uses_raw_fetch_not_docling(self):
        import convert as C
        import tempfile
        from pathlib import Path
        from unittest import mock
        url = "https://raw.githubusercontent.com/acme/laws/main/kr/%EB%B2%95/a.md"
        with tempfile.TemporaryDirectory() as td, mock.patch.object(C, "_github_text_fallback", return_value=self.NESTED), \
                mock.patch.object(C.shutil, "which", return_value=None), mock.patch.object(C._pd, "extract_all", side_effect=RuntimeError("no net")):
            rec = C.convert(url, Path(td) / "raw")
            self.assertEqual(rec["status"], "ok", rec["error"])
            files = list((Path(td) / "raw").glob("*.md"))
            self.assertEqual(len(files), 1)
            text = files[0].read_text(encoding="utf-8")
        self.assertIn("converter: raw-fetch", text)
        self.assertIn("갑의 둘째 목 문장", text)

    def test_non_markdown_sources_still_need_docling(self):
        import convert as C
        import tempfile
        from pathlib import Path
        from unittest import mock
        with tempfile.TemporaryDirectory() as td, mock.patch.object(C.shutil, "which", return_value=None):
            rec = C.convert("https://example.org/paper.pdf", Path(td) / "raw")
        self.assertEqual(rec["status"], "error")
        self.assertIn("docling", rec["error"])

    def test_markdown_url_falls_back_to_docling_when_fetch_fails(self):
        import convert as C
        from unittest import mock
        with mock.patch.object(C, "_github_text_fallback", side_effect=OSError("offline")):
            self.assertIsNone(C._markdown_passthrough("https://raw.githubusercontent.com/a/b/main/x.md"))
