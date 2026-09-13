#!/usr/bin/env python3
"""Validate asserted Turtle, then optionally emit a derived inferred Turtle graph."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import ttl_reason
from ttl_validate import validate_target


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TTL-only validation and reasoning pipeline")
    ap.add_argument("--target", required=True, type=Path)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--gates-only", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    paths, graph, failures = validate_target(args.target, args.domain)
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print(f"PASS gates: {len(paths)} asserted TTL file(s), {len(graph)} triples")
    if args.gates_only:
        return 0
    return ttl_reason.main([
        "--target", str(args.target),
        "--domain", args.domain,
        *(["--apply"] if args.apply else []),
    ])


if __name__ == "__main__":
    raise SystemExit(main())
