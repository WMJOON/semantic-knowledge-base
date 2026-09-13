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

RAW_REL = "evidence/raw"
_DOCLING_HINT = "docling 필요: uv tool install docling  (https://github.com/docling-project/docling)"
_TIMEOUT_S = 600

# docling HTML 변환 시 섞여 나오는 이미지 플레이스홀더 주석
_IMG_PLACEHOLDER = re.compile(r"<!--\s*🖼️❌[^>]*-->\s*\n?")


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
    """docling 산출 MD 후처리: 이미지 플레이스홀더 제거 + 과잉 공백 축소."""
    text = _IMG_PLACEHOLDER.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


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
            proc = subprocess.run(
                ["docling", source, "--to", "md", "--output", td],
                capture_output=True, text=True, timeout=_TIMEOUT_S,
            )
            if proc.returncode != 0:
                rec.update(status="error", error=(proc.stderr or proc.stdout)[-300:])
                return rec
            produced = sorted(Path(td).glob("*.md"))
            if not produced:
                rec.update(status="error", error="docling 이 .md 산출물을 생성하지 않음")
                return rec
            body = _clean_markdown(produced[0].read_text(encoding="utf-8"))

        out = raw_dir / f"{_slug(origin)}.md"
        frontmatter = (
            "---\n"
            f"source: {origin}\n"
            f"converted_at: {rec['converted_at']}\n"
            "converter: docling\n"
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
