#!/usr/bin/env python3
"""SPEC §7: optional skill-link health.

When `--with-skill-links` was applied, validate that the expected symlinks
exist and point to real directories. By default the check is skipped (PASS),
since AC-RS-6 requires no $HOME mutation in the default flow.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

EXPECTED_HOME_LINKS = (
    "~/.claude/skills",
    "~/.claude/skills/skb-orchestration",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--with-skill-links", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    if not args.with_skill_links:
        print("SKIP: --with-skill-links not requested")
        return 0

    bad: list[str] = []
    for raw in EXPECTED_HOME_LINKS:
        p = Path(os.path.expanduser(raw))
        if not p.exists():
            bad.append(f"missing: {p}")
            continue
        if p.is_symlink() and not p.resolve().exists():
            bad.append(f"broken symlink: {p}")
    if bad:
        for b in bad:
            print(f"FAIL: {b}", file=sys.stderr)
        return 1 if args.strict else 0
    print("OK: skill links healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
