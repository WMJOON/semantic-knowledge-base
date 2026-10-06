#!/usr/bin/env python3
"""docling 변환 스테이지 for skb-evidence (v1.1.0).

원문(정적 URL, 로컬 HTML/PDF/DOCX/XLSX/PPTX, 렌더링된 HTML 스냅샷)을
docling CLI로 Markdown 원문으로 변환해 <target>/evidence/raw/ 에 저장한다.

설계 원칙 (capture.py 와 동일):
  - **opt-in 외부 CLI**: docling 은 subprocess 호출 — 이 스크립트를 쓰지 않는
    코어 collect 경로는 여전히 stdlib-only.
  - **graceful degrade**: docling 부재·변환 실패 시 status="error" +
    actionable hint 를 반환하고 파이프라인을 중단시키지 않는다.
  - **provenance**: 변환 산출 MD 에 YAML frontmatter(source/converted_at/converter)를
    남긴다. collect 는 청킹 시 frontmatter 를 strip 하므로 seed 본문은 오염되지 않는다.

Usage:
  python3 scripts/convert.py --source <URI|FILE> --target <KB_ROOT>
  python3 scripts/convert.py --source <FILE> --source-url <원본 URL> --target <KB_ROOT>
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as _layout_mod  # noqa: E402
import provenance_dates as _pd  # noqa: E402

RAW_REL = "evidence/raw"
_DOCLING_HINT = "docling 필요: uv tool install docling  (https://github.com/docling-project/docling)"
_TIMEOUT_S = 600

# docling HTML 변환 시 섞여 나오는 이미지 플레이스홀더 주석
_IMG_PLACEHOLDER = re.compile(r"<!--\s*🖼️❌[^>]*-->\s*\n?")

# docling 기본값(embedded)이 PDF 그림을 data URI(base64)로 본문에 넣는다. 청킹이 이 긴 문자열을
# 잘라 seed 대부분을 이미지 조각으로 채우므로(2026-09-30 mixed-precision 리서치 사례: seed 80%)
# 반드시 제거한다.
_DATA_URI_IMG = re.compile(r"!\[[^\]]*\]\(data:image/[a-zA-Z0-9+.-]+;base64,[A-Za-z0-9+/=\s]+\)")
_GITHUB_BLOB = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$")
_TEXT_EXT = {"md", "markdown", "txt", "rst", "py", "cpp", "c", "h", "hpp", "js", "ts", "json", "yaml", "yml", "toml", "sh"}


def _utc_now() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha12(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _slug(source: str) -> str:
    """URI/경로에서 결정적 슬러그 생성 (max 40 chars + sha12 suffix)."""
    import urllib.parse

    lower = source.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        parsed = urllib.parse.urlparse(source)
        base = (parsed.hostname or "") + "_" + parsed.path.strip("/").replace("/", "_")
    else:
        base = Path(source).stem
    base = re.sub(r"[^a-zA-Z0-9가-힣._-]", "-", base).strip("-_.")[:40] or "source"
    return f"{base}__{_sha12(source)}"


def _clean_markdown(text: str) -> str:
    """docling 산출 MD 후처리: 이미지 플레이스홀더·data URI 이미지 제거 + 과잉 공백 축소."""
    text = _IMG_PLACEHOLDER.sub("", text)
    text = _DATA_URI_IMG.sub("[image omitted]", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def _github_text_fallback(source: str) -> str | None:
    """GitHub blob/raw 텍스트 소스를 docling 이 못 만들 때 raw 내용을 직접 받는다(md 는 그대로, 코드는 펜스).

    docling 은 github.com/.../blob/... HTML 페이지나 .py/.cpp 같은 코드에서 산출물을 만들지 못한다.
    """
    import urllib.request

    m = _GITHUB_BLOB.match(source)
    if m:
        fetch = f"https://raw.githubusercontent.com/{m[1]}/{m[2]}/{m[3]}/{m[4]}"
    elif source.startswith("https://raw.githubusercontent.com/"):
        fetch = source
    else:
        return None
    ext = fetch.rsplit(".", 1)[-1].lower() if "." in fetch.rsplit("/", 1)[-1] else ""
    if ext not in _TEXT_EXT:
        return None
    req = urllib.request.Request(fetch, headers={"User-Agent": "skb-evidence/raw-fetch"})
    text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    if ext in ("md", "markdown", "txt", "rst"):
        return text
    return f"```{ext}\n{text.rstrip()}\n```\n"


def convert(source: str, raw_dir: Path, source_url: str | None = None,
            rel_prefix: str | None = None) -> dict:
    """단일 source 를 docling 으로 MD 변환.

    Args:
      source: 정적 URL 또는 로컬 파일 경로 (HTML/PDF/DOCX/XLSX/PPTX/MD 등 docling 지원 포맷)
      raw_dir: 산출 디렉토리 (기본 <target>/evidence/raw)
      source_url: source 가 렌더링 스냅샷 등 중간 파일일 때의 원본 URL (provenance 용)
      rel_prefix: rec["md"] 에 기록할 KB-상대 디렉토리. 미지정 시 RAW_REL 기본값

    Returns:
      {source, source_url, md, converted_at, status, error}
      - md: raw_dir 기준이 아닌 KB-relative 경로 문자열 (status=ok 일 때만)
    """
    origin = source_url or source
    collected_at = _utc_now()            # 수집일: 원문을 가져오기 시작하는 순간(v1.1.4, 반드시 표기)
    rec = {
        "source": source, "source_url": origin, "md": None,
        "converted_at": _utc_now(), "status": "ok", "error": None,
    }

    if shutil.which("docling") is None:
        rec.update(status="error", error=_DOCLING_HINT)
        return rec

    try:
        raw_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="skb-convert-") as td:
            base_cmd = ["docling", source, "--to", "md", "--output", td]
            proc = subprocess.run(
                base_cmd + ["--image-export-mode", "placeholder"],
                capture_output=True, text=True, timeout=_TIMEOUT_S,
            )
            if proc.returncode != 0 and "image-export-mode" in (proc.stderr or proc.stdout or ""):
                # 옵션을 모르는 docling 버전: 플래그 없이 재시도(본문 data URI는 _clean_markdown 이 제거)
                proc = subprocess.run(base_cmd, capture_output=True, text=True, timeout=_TIMEOUT_S)
            if proc.returncode != 0:
                rec.update(status="error", error=(proc.stderr or proc.stdout)[-300:])
                return rec
            produced = sorted(Path(td).glob("*.md"))
            if not produced:
                fb = _github_text_fallback(source)
                if fb is None:
                    rec.update(status="error", error="docling 이 .md 산출물을 생성하지 않음")
                    return rec
                rec["converter"] = "raw-fetch"
                fallback_body = fb
            body = _clean_markdown(fallback_body if not produced else produced[0].read_text(encoding="utf-8"))

        # 제공자가 선언한 발행일(추정 금지). 렌더링 스냅샷(.html)이 있으면 그 HTML 을 쓴다(봇 차단 우회).
        try:
            snap = Path(source)
            html = snap.read_text(encoding="utf-8", errors="replace") if snap.suffix == ".html" and snap.is_file() else None
            meta = _pd.extract_all(origin, html)
        except Exception as e:  # noqa: BLE001  발행일·발행 주체 조회 실패가 수집을 막지 않는다. 실패는 사유로 남긴다.
            meta = {"published_at": None, "published_at_source": f"none:extract-error-{type(e).__name__}",
                    "publisher": _pd._host(origin) or "unknown", "publisher_source": "domain-derived",
                    "authors": [], "authors_source": f"none:extract-error-{type(e).__name__}",
                    "publisher_type": "unknown", "publisher_type_source": "none:extract-error",
                    "accounts": [], "accounts_source": f"none:extract-error-{type(e).__name__}",
                    "document_type": "unknown", "document_type_source": "none:extract-error"}
        published, pub_src = meta["published_at"], meta["published_at_source"]
        out = raw_dir / f"{_slug(origin)}.md"
        frontmatter = (
            "---\n"
            f"source: {origin}\n"
            f"collected_at: {collected_at}\n"
            "collected_at_basis: fetch-time\n"
            f"published_at: {published or 'unavailable'}\n"
            f"published_at_source: {pub_src}\n"
            f"publisher: {meta['publisher']}\n"
            f"publisher_source: {meta['publisher_source']}\n"
            f"publisher_type: {meta['publisher_type']}\n"
            f"publisher_type_source: {meta['publisher_type_source']}\n"
            f"authors: {__import__('json').dumps(meta['authors'], ensure_ascii=False)}\n"
            f"authors_source: {meta['authors_source']}\n"
            f"accounts: {__import__('json').dumps(meta['accounts'], ensure_ascii=False)}\n"
            f"accounts_source: {meta['accounts_source']}\n"
            f"document_type: {meta['document_type']}\n"
            f"document_type_source: {meta['document_type_source']}\n"
            f"converted_at: {rec['converted_at']}\n"
            f"converter: {rec.get('converter', 'docling')}\n"
            "---\n\n"
        )
        out.write_text(frontmatter + body, encoding="utf-8")
        rec["md"] = f"{rel_prefix or RAW_REL}/{out.name}"
    except subprocess.TimeoutExpired:
        rec.update(status="error", error=f"docling 변환 timeout ({_TIMEOUT_S}s)")
    except Exception as e:  # noqa: BLE001
        rec.update(status="error", error=str(e)[:300])
    return rec


def convert_to_target(source: str, target: Path, source_url: str | None = None) -> dict:
    """layout 의 raw_dir 에 변환. ingest.py 가 호출하는 공개 진입점."""
    raw_dir = _layout_mod.resolve_layout(target)["raw_dir"]
    return convert(source, raw_dir, source_url=source_url,
                   rel_prefix=_layout_mod.rel(target, raw_dir))


def main() -> int:
    ap = argparse.ArgumentParser(prog="convert")
    ap.add_argument("--source", required=True, help="정적 URL 또는 로컬 파일 경로")
    ap.add_argument("--target", default=".", help="KB root (출력: <target>/evidence/raw/)")
    ap.add_argument("--source-url", default=None, help="중간 파일 변환 시 원본 URL (provenance)")
    args = ap.parse_args()

    rec = convert_to_target(args.source, Path(args.target).resolve(), source_url=args.source_url)
    if rec["status"] == "ok":
        print(f"[ok] {rec['source_url']} -> {rec['md']}")
        return 0
    print(f"ERROR: {rec['source_url']}: {rec['error']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
