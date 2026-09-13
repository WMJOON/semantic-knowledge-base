#!/usr/bin/env python3
"""Guard the TTL-only boundary: maintenance plans never mutate ontology data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rewrite")
    parser.add_argument("--target", required=True)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    try:
        plan = json.loads(args.plan.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read plan: {exc}", file=sys.stderr)
        return 2
    if plan.get("auto_fixes"):
        print(
            "FAIL: TTL-only maintenance does not apply ontology auto-fixes; "
            "review hitl_required and use skb-ontology after approval",
            file=sys.stderr,
        )
        return 2
    result = {
        "run_id": args.run_id or plan.get("plan_id"),
        "applied": [],
        "dry_run": not args.apply,
        "message": "No automatic TTL rewrite is permitted.",
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
