#!/usr/bin/env python3
"""SPEC §8.1: root writable + required directories."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def detect_layout(target: Path) -> str:
    """hub 가 layout: 의 semantic_dir 를 선언하면 b1, 아니면 legacy."""
    hub = target / "canonical_root_hub.yaml"
    if hub.exists() and re.search(r"^layout:\s*\n(?:[ \t]+.*\n)*?[ \t]+semantic_dir:", hub.read_text(encoding="utf-8"), re.M):
        return "b1"
    return "legacy"


def required_dirs(target: Path) -> list[str]:
    """필수 디렉토리는 스캐폴드 manifest 에서 가져온다 — 목록을 두 곳에 두면 갈라진다."""
    sys.path.insert(0, str(SCRIPTS))
    from manifest import build_manifest  # noqa: E402
    return [e.path for e in build_manifest(targets=("claude",), layout=detect_layout(target)) if e.kind == "dir"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    args = ap.parse_args()
    target = Path(args.target).resolve()
    if not target.exists() or not os.access(target, os.W_OK):
        print(f"FAIL: target not writable: {target}", file=sys.stderr)
        return 1
    required = required_dirs(target)
    missing = [d for d in required if not (target / d).is_dir()]
    if missing:
        print("FAIL: missing required directories:", file=sys.stderr)
        for d in missing:
            print(f"  - {d}", file=sys.stderr)
        return 1
    print(f"OK: {len(required)} required directories present at {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
