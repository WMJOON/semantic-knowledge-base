#!/usr/bin/env python3
"""Oracle repository_integrity: 스캐폴드가 갖춰야 할 구조(디렉토리·hub·워크플로우·메모리·하네스)의 충족도.

score_readiness 의 가중 점수를 하네스 oracle 계약으로 감싼다.
하네스 oracle 계약: evaluate(target, run_context=None) -> {"score", "passed", "details"}.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from score_readiness import score  # noqa: E402


def evaluate(target: Path, run_context: dict | None = None) -> dict:
    result = score(Path(target).resolve())
    return {
        "score": result["score"],
        "passed": result["gate"] == "pass",
        "details": {"gate": result["gate"], "breakdown": result["breakdown"]},
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, type=Path)
    args = ap.parse_args(argv)
    out = evaluate(args.target)
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
