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
