#!/usr/bin/env python3
"""raw-ingest 오케스트레이터 for skb-evidence (v1.1.0).

Flow: [render(playwright-cli, opt)] → convert(docling) → collect(청킹·dedup·seed).

기존 collect 가 커버하지 못하던 두 소스 유형을 닫는다:
  - JS-rendered 페이지: --render 로 playwright-cli 가 렌더링된 DOM 을
    evidence/captures/<sha12>.html 로 박제한 뒤 변환 입력으로 사용
  - PDF/Office 문서(+정적 URL): docling 이 Markdown 원문으로 변환해
    evidence/raw/ 에 저장

설계 원칙:
  - **opt-in 외부 CLI**: playwright-cli(npm), docling — subprocess 호출.
    코어 collect 경로(stdlib-only)는 불변.
  - **graceful degrade**: CLI 부재 시 소스 단위로 status="error" + actionable
    hint 를 남기고 나머지 소스는 계속 처리한다.
  - 변환 산출 MD 는 collect 파이프라인에 로컬 소스로 투입되어 기존
    청킹·dedup·seed 계약을 그대로 따른다.

Usage:
  python3 scripts/ingest.py --target REPO --source URI [URI ...] [--render] [--apply] [--cluster X]

도구 스택 결정 근거: consumer KB work-memory AD-0021 / UD-0031
(playwright-cli + docling 2-도구 CLI, firecrawl 불채택).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import collect as _collect  # noqa: E402
import convert as _convert  # noqa: E402
import layout as _layout_mod  # noqa: E402

CAPTURES_REL = "evidence/captures"
_PW_SESSION = "skb-ingest"
_PW_HINT = "playwright-cli 필요: npm install -g @playwright/cli  (렌더링 opt-in 경로에서만 사용)"
_PW_TIMEOUT_S = 120


def _sha12(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _is_url(source: str) -> bool:
    lower = source.lower()
    return lower.startswith("http://") or lower.startswith("https://")


def _pw(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["playwright-cli", f"-s={_PW_SESSION}", *args],
        capture_output=True, text=True, timeout=_PW_TIMEOUT_S,
    )


def _parse_eval_output(raw: str) -> str:
    """playwright-cli eval 출력 파싱: '### Result' 헤더 + JSON 문자열 언이스케이프."""
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith('"') and line.endswith('"'):
            return json.loads(line)
    s, e = raw.find('"'), raw.rfind('"')
    if 0 <= s < e:
        return json.loads(raw[s:e + 1])
    raise ValueError("playwright-cli eval 출력에서 HTML 문자열을 찾지 못함")


def render_url(url: str, captures_dir: Path) -> dict:
    """playwright-cli 로 렌더링된 DOM 을 <captures_dir>/<sha12>.html 로 저장.

    Returns: {url, html, status, error} — html 은 절대경로 문자열 (status=ok 시).
    """
    rec = {"url": url, "html": None, "status": "ok", "error": None}
    if shutil.which("playwright-cli") is None:
        rec.update(status="error", error=_PW_HINT)
        return rec
    try:
        captures_dir.mkdir(parents=True, exist_ok=True)
        _pw(["open", url])
        out = _pw(["eval", "document.documentElement.outerHTML"])
        html = _parse_eval_output(out.stdout)
        dest = captures_dir / f"{_sha12(url)}.html"
        dest.write_text(html, encoding="utf-8")
        rec["html"] = str(dest)
    except Exception as e:  # noqa: BLE001
        rec.update(status="error", error=str(e)[:300])
    finally:
        try:
            _pw(["close"])
        except Exception:  # noqa: BLE001
            pass
    return rec


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="ingest")
    p.add_argument("--target", default=".", help="KB root path")
    p.add_argument("--source", nargs="+", default=[], metavar="URI")
    p.add_argument("--sources-file", default=None, metavar="PATH")
    p.add_argument("--render", action="store_true", default=False,
                   help="URL 을 playwright-cli 로 렌더링 후 변환 (JS-rendered 페이지용, opt-in)")
    p.add_argument("--cluster", default=None)
    p.add_argument("--chunk-size", type=int, default=1200)
    p.add_argument("--chunk-overlap", type=int, default=100)
    p.add_argument("--dry-run", action="store_true", default=False)
    p.add_argument("--apply", action="store_true", default=False)
    p.add_argument("--run-id", default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    target = Path(args.target).resolve()

    uris: list[str] = list(args.source)
    if args.sources_file:
        sf = Path(args.sources_file)
        if sf.exists():
            for line in sf.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    uris.append(line)
    if not uris:
        print("No sources specified.", file=sys.stderr)
        return 2

    converted: list[str] = []
    errors = 0
    for uri in uris:
        source_url = None
        conv_input = uri
        if _is_url(uri) and args.render:
            rendered = render_url(
                uri, _layout_mod.resolve_layout(target)["captures_dir"])
            if rendered["status"] != "ok":
                print(f"ERROR: render {uri}: {rendered['error']}", file=sys.stderr)
                errors += 1
                continue
            print(f"[render] {uri} -> {rendered['html']}")
            conv_input, source_url = rendered["html"], uri

        rec = _convert.convert_to_target(conv_input, target, source_url=source_url)
        if rec["status"] != "ok":
            print(f"ERROR: convert {uri}: {rec['error']}", file=sys.stderr)
            errors += 1
            continue
        print(f"[convert] {rec['source_url']} -> {rec['md']}")
        converted.append(str(target / rec["md"]))

    if not converted:
        print("\nSummary: converted=0 — collect 단계 생략", file=sys.stderr)
        return 1

    collect_argv = ["--target", str(target), "--source", *converted,
                    "--chunk-size", str(args.chunk_size),
                    "--chunk-overlap", str(args.chunk_overlap)]
    if args.cluster:
        collect_argv += ["--cluster", args.cluster]
    if args.apply and not args.dry_run:
        collect_argv.append("--apply")
    if args.run_id:
        collect_argv += ["--run-id", args.run_id]

    rc = _collect.main(collect_argv)
    return 1 if errors else rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
