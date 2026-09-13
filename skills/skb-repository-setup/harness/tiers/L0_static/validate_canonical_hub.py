#!/usr/bin/env python3
"""SPEC §8.1 + canonical-hub-SPEC §4: canonical_root_hub.yaml schema check.

Text-based check avoids a hard pyyaml dep. Verifies presence of required keys,
locked default, and the v0.10.0 sync invariants.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQUIRED_KEYS = (
    "version:",
    "locked:",
    "domains:",
    "scan:",
    "sync:",
)
SYNC_INVARIANTS = (
    ("structural_ssot:", "ttl"),
    ("projection_target:", "md"),
    ("auto_apply_md_to_ttl:", "false"),
)
SCAN_INVARIANTS = ("include:", "exclude:")

DOMAIN_BLOCK_RE = re.compile(
    r"-\s*name:\s*([a-z][a-z0-9-]*)\s*(?:\n[^-].*)*", re.MULTILINE
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    args = ap.parse_args()
    target = Path(args.target).resolve()
    hub = target / "canonical_root_hub.yaml"
    if not hub.exists():
        print("FAIL: canonical_root_hub.yaml not found", file=sys.stderr)
        return 1
    text = hub.read_text(encoding="utf-8")
    missing = [k for k in REQUIRED_KEYS if k not in text]
    if missing:
        print(f"FAIL: missing keys: {missing}", file=sys.stderr)
        return 1
    for key, value in SYNC_INVARIANTS:
        m = re.search(rf"{re.escape(key)}\s*([^\n]+)", text)
        if not m:
            print(f"FAIL: sync.{key} missing", file=sys.stderr)
            return 1
        if value not in m.group(1):
            print(f"FAIL: sync.{key} != {value} (got: {m.group(1).strip()})", file=sys.stderr)
            return 1
    for key in SCAN_INVARIANTS:
        if key not in text:
            print(f"FAIL: scan.{key} missing", file=sys.stderr)
            return 1
    # locked must be true
    if not re.search(r"locked:\s*true", text):
        print("FAIL: locked must be true at v0.10.0", file=sys.stderr)
        return 1
    # validate domains[].name are kebab-case if present
    for m in DOMAIN_BLOCK_RE.finditer(text):
        name = m.group(1)
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            print(f"FAIL: domain name not kebab-case: {name}", file=sys.stderr)
            return 1
        # root_hub file must exist
        root_hub_re = re.search(
            rf"-\s*name:\s*{re.escape(name)}.*?root_hub:\s*\"([^\"]+)\"",
            text,
            re.DOTALL,
        )
        if root_hub_re:
            root_hub_path = target / root_hub_re.group(1)
            if not root_hub_path.exists():
                print(f"FAIL: domain {name} root_hub missing: {root_hub_path}", file=sys.stderr)
                return 1
    print(f"OK: canonical_root_hub.yaml valid at {hub}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
