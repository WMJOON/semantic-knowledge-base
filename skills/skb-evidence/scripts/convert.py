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


_MARKDOWN_EXT = {"md", "markdown", "txt", "rst"}


def _markdown_passthrough(source: str) -> tuple[str, str] | None:
    """이미 마크다운·텍스트인 원문은 docling 을 거치지 않고 그대로 쓴다. (본문, converter 이름) 또는 None.

    docling 은 마크다운 입력의 중첩 목록(가·나·다 목, 호 아래 목)과 일부 표 안 문장을 조용히 떨어뜨린다. 법령 마크다운(legalize-kr)에서
    조문 10개 · 최대 4,700자가 사라진 것을 확인했다(2026-10-06). 원문이 이미 텍스트면 변환할 이유가 없고 변환은 손실만 만든다.
    GitHub raw/blob 텍스트와 로컬 .md/.txt 가 대상이다. 그 밖의 형식(HTML·PDF·Office)은 docling 이 맡는다.
    """
    if source.lower().startswith(("http://", "https://")):
        ext = source.split("?", 1)[0].rsplit(".", 1)[-1].lower() if "." in source.rsplit("/", 1)[-1] else ""
        if ext not in _MARKDOWN_EXT:
            return None
        try:
            text = _github_text_fallback(source)
        except Exception:  # noqa: BLE001  네트워크 실패는 docling 경로로 넘긴다
            return None
        return (text, "raw-fetch") if text is not None else None
    p = Path(source)
    if p.is_file() and p.suffix.lower().lstrip(".") in _MARKDOWN_EXT:
        return p.read_text(encoding="utf-8"), "passthrough"
    return None


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


_MEDIA_BY_SUFFIX = {".html": "text/html", ".htm": "text/html", ".pdf": "application/pdf", ".md": "text/markdown", ".markdown": "text/markdown",
                    ".txt": "text/plain", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _request_frontmatter(source: str, origin: str, source_url: str | None, search: dict | None, params: dict | None) -> str:
    """원문 노트 frontmatter 의 요청 조건 줄. 도구가 아는 값만 쓴다.

    request_url: 원본 URL(http). media_type/response_sha256: 입력이 로컬 파일일 때만(원격 URL 은 docling 이 직접 받아 응답을 우리가 보지 못한다).
    렌더링 스냅샷(source_url 이 있는 경우)의 해시는 HTTP 응답이 아니라 렌더링 결과라서 싣지 않는다.
    """
    import hashlib
    import json as _json
    lines: list[str] = []
    if origin.lower().startswith(("http://", "https://")):
        lines.append(f"request_url: {origin}")
    p = Path(source)
    if not source.lower().startswith(("http://", "https://")) and p.is_file():
        mt = _MEDIA_BY_SUFFIX.get(p.suffix.lower())
        if mt:
            lines.append(f"media_type: {mt}")
        if source_url is None:
            lines.append(f"response_sha256: {hashlib.sha256(p.read_bytes()).hexdigest()}")
    elif source_url is not None:
        lines.append("media_type: text/html")  # 렌더링 스냅샷
    if search:
        lines.append(f"searched_at: {search['searched_at']}")
        lines.append(f"search_query: {search['search_query'].splitlines()[0] if search['search_query'] else ''}")
    if params:
        lines.append(f"request_params: {_json.dumps(params, ensure_ascii=False, sort_keys=True)}")
    return "".join(ln + "\n" for ln in lines)


def _docling_body(source: str, rec: dict) -> str | None:
    """docling 으로 변환한 본문. 실패하면 rec 에 사유를 적고 None."""
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
            return None
        produced = sorted(Path(td).glob("*.md"))
        if not produced:
            fb = _github_text_fallback(source)
            if fb is None:
                rec.update(status="error", error="docling 이 .md 산출물을 생성하지 않음")
                return None
            rec["converter"] = "raw-fetch"
            return _clean_markdown(fb)
        return _clean_markdown(produced[0].read_text(encoding="utf-8"))


def convert(source: str, raw_dir: Path, source_url: str | None = None,
            rel_prefix: str | None = None, search: dict | None = None, params: dict | None = None) -> dict:
    """단일 source 를 MD 로 변환. 이미 마크다운·텍스트인 원문(GitHub raw/blob, 로컬 .md/.txt)은 docling 을 거치지 않고 그대로 쓴다(변환 손실 방지).

    Args:
      source: 정적 URL 또는 로컬 파일 경로 (HTML/PDF/DOCX/XLSX/PPTX/MD 등 docling 지원 포맷)
      raw_dir: 산출 디렉토리 (기본 <target>/evidence/raw)
      source_url: source 가 렌더링 스냅샷 등 중간 파일일 때의 원본 URL (provenance 용)
      rel_prefix: rec["md"] 에 기록할 KB-상대 디렉토리. 미지정 시 RAW_REL 기본값
      search: {"searched_at", "search_query"} — 검색으로 찾은 경우만 frontmatter 에 싣는다
      params: API 요청 파라미터(JSON 객체) — frontmatter 에 request_params 로 싣는다

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

    pt = _markdown_passthrough(source)
    if pt is None and shutil.which("docling") is None:
        rec.update(status="error", error=_DOCLING_HINT)
        return rec

    try:
        raw_dir.mkdir(parents=True, exist_ok=True)
        if pt is not None:
            rec["converter"] = pt[1]
            body = _clean_markdown(pt[0])
        else:
            body = _docling_body(source, rec)
            if body is None:
                return rec

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
        req = _request_frontmatter(source, origin, source_url, search, params)
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
            f"{req}"
            "---\n\n"
        )
        out.write_text(frontmatter + body, encoding="utf-8")
        rec["md"] = f"{rel_prefix or RAW_REL}/{out.name}"
    except subprocess.TimeoutExpired:
        rec.update(status="error", error=f"docling 변환 timeout ({_TIMEOUT_S}s)")
    except Exception as e:  # noqa: BLE001
        rec.update(status="error", error=str(e)[:300])
    return rec


def convert_to_target(source: str, target: Path, source_url: str | None = None,
                      search: dict | None = None, params: dict | None = None) -> dict:
    """layout 의 raw_dir 에 변환. ingest.py 가 호출하는 공개 진입점."""
    raw_dir = _layout_mod.resolve_layout(target)["raw_dir"]
    return convert(source, raw_dir, source_url=source_url,
                   rel_prefix=_layout_mod.rel(target, raw_dir), search=search, params=params)


def main() -> int:
    ap = argparse.ArgumentParser(prog="convert")
    ap.add_argument("--source", required=True, help="정적 URL 또는 로컬 파일 경로")
    ap.add_argument("--target", default=".", help="KB root (출력: <target>/evidence/raw/)")
    ap.add_argument("--source-url", default=None, help="중간 파일 변환 시 원본 URL (provenance)")
    ap.add_argument("--searched-at", default=None, metavar="ISO_Z", help="검색으로 찾은 시각(UTC). --search-query 와 함께")
    ap.add_argument("--search-query", default=None)
    ap.add_argument("--request-params", default=None, metavar="JSON")
    args = ap.parse_args()
    import retrieval_meta as _rm
    bad = _rm.check_search(args.searched_at, args.search_query)
    params, perr = _rm.check_params(args.request_params)
    if bad or perr:
        print(f"ERROR: {bad or perr}", file=sys.stderr)
        return 2
    search = {"searched_at": args.searched_at, "search_query": args.search_query} if args.searched_at else None

    rec = convert_to_target(args.source, Path(args.target).resolve(), source_url=args.source_url, search=search, params=params)
    if rec["status"] == "ok":
        print(f"[ok] {rec['source_url']} -> {rec['md']}")
        return 0
    print(f"ERROR: {rec['source_url']}: {rec['error']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
