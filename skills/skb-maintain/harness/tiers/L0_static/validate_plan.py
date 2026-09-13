#!/usr/bin/env python3
"""L0 static validator for skb-maintain.

AC-MN-6: Static structure check — verifies required directories exist.
Does NOT run scan (L0 = static check).

Checks:
- ontology/system/semantic/ exists and its asserted Turtle validates
- evidence/ exists (may be empty, seeds.jsonl optional)
- harness/ exists

Exit 0 = structure OK (no critical drift).
Exit 1 = structural violation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED_DIRS = [
    "ontology/system/semantic",
    "evidence",
    "harness",
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="validate_plan")
    p.add_argument("--target", required=True)
    return p.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    target = Path(args.target).resolve()

    failures: list[str] = []

    if not target.exists():
        print(f"FAIL: target does not exist: {target}", file=sys.stderr)
        return 1

    for rel in REQUIRED_DIRS:
        path = target / rel
        if not path.exists():
            failures.append(f"missing required directory: {rel}")

    if not failures:
        ontology_scripts = Path(__file__).resolve().parents[4] / "skb-ontology" / "scripts"
        sys.path.insert(0, str(ontology_scripts))
        from ttl_validate import validate_target
        _, _, ttl_failures = validate_target(target)
        failures.extend(f"TTL {failure}" for failure in ttl_failures)

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        print(f"FAIL: {len(failures)} structural issue(s) at {target}", file=sys.stderr)
        return 1

    print(f"OK: target structure valid at {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
