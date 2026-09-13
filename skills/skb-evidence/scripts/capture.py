#!/usr/bin/env python3
"""skb-evidence capture — 출처 URL 원문 박제(PDF+PNG+HTML) + captured_at 기록.

홈페이지·프로필 사이트는 시점에 따라 내용이 바뀌거나 사라진다. 검증 시점의 원문을
스냅샷으로 보존해 Sorcelink(1차 출처 검증)를 사후에도 재검증 가능하게 한다.

산출: <target>/evidence/captures/<sha12>.{pdf,png,html}  + stdout 메타데이터 JSON 1줄.
  sha12 = sha256(url)[:12]

설계 (PRD v0.12.2):
  - **opt-in 무거운 로컬 컴포넌트**: playwright 는 lazy import — 이 스크립트(또는
    collect --capture)가 실제 호출될 때만 import. 코어 stdlib 경로 불변.
  - **graceful degrade**: playwright 부재·타임아웃·로드 실패 시 status="error" +
    actionable 메시지 기록. 호출측(collect)은 텍스트 수집을 계속한다.

Usage:
  python3 scripts/capture.py --url <URL> --target <REPO>
  python3 scripts/capture.py --url <URL> --outdir <DIR>   # 직접 출력 경로 지정
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as _layout_mod  # noqa: E402

TOOL_VERSION = "skb-evidence/1.0.0"  # MSM spec 축 (package 축 0.12.2 와 별개)

CAPTURES_REL = "evidence/captures"
_PLAYWRIGHT_HINT = (
    "playwright 필요: pip install playwright && playwright install chromium"
)


def _sha12(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


def _utc_now() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def capture(url: str, captures_dir: Path, rel_prefix: str = CAPTURES_REL) -> dict:
    """단일 URL 캡처. 산출 경로는 captures_dir, 기록 경로는 rel_prefix 기준.

    Returns 메타데이터 dict:
      {url, sha, captured_at, status, pdf, png, html, title, error}
      - status: "ok" | "error"
      - pdf/png/html: rel_prefix 기준 상대경로 (status=ok 일 때만 채워짐)
    """
    sha = _sha12(url)
    rec = {
        "url": url, "sha": sha, "captured_at": _utc_now(), "status": "ok",
        "pdf": None, "png": None, "html": None, "title": None, "error": None,
    }

    # lazy import — --capture 미사용 경로에서는 import 자체가 일어나지 않음
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        rec.update(status="error", error=_PLAYWRIGHT_HINT)
        return rec

    try:
        captures_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 1600})
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)  # settle
            rec["title"] = page.title()
            pdf = captures_dir / f"{sha}.pdf"
            png = captures_dir / f"{sha}.png"
            html = captures_dir / f"{sha}.html"
            page.pdf(path=str(pdf), format="A4", print_background=True)
            page.screenshot(path=str(png), full_page=True)
            html.write_text(page.content(), encoding="utf-8")
            browser.close()
        rec.update(
            pdf=f"{rel_prefix}/{sha}.pdf",
            png=f"{rel_prefix}/{sha}.png",
            html=f"{rel_prefix}/{sha}.html",
        )
    except Exception as e:  # noqa: BLE001
        rec.update(status="error", error=str(e)[:300])
    return rec


def capture_to_target(url: str, target: Path) -> dict:
    """layout 의 captures_dir 에 캡처. collect.py 가 호출하는 공개 진입점."""
    captures_dir = _layout_mod.resolve_layout(target)["captures_dir"]
    return capture(url, captures_dir, _layout_mod.rel(target, captures_dir))


def main() -> int:
    ap = argparse.ArgumentParser(prog="capture",
                                 description="URL 원문 스냅샷 (PDF+PNG+HTML)")
    ap.add_argument("--url", required=True, help="캡처할 URL")
    ap.add_argument("--target", default=None, help="KB 루트 (기본 출력: <target>/evidence/captures)")
    ap.add_argument("--outdir", default=None, help="출력 디렉토리 직접 지정 (--target 대체)")
    args = ap.parse_args()

    if args.outdir:
        out = Path(args.outdir)
        rec = capture(args.url, out, str(out))
    elif args.target:
        rec = capture_to_target(args.url, Path(args.target).resolve())
    else:
        out = Path.cwd() / CAPTURES_REL
        rec = capture(args.url, out, CAPTURES_REL)

    print(json.dumps(rec, ensure_ascii=False))
    if rec["status"] == "error" and rec.get("error") == _PLAYWRIGHT_HINT:
        print(_PLAYWRIGHT_HINT, file=sys.stderr)
    return 0 if rec["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
