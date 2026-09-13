#!/usr/bin/env python3
"""L0 static validator for evidence/seeds.jsonl.

Checks:
- seeds.jsonl is valid JSONL (each line is valid JSON) if it exists
- each seed has required fields: id, kind, uri, content_hash, chunk, md_path
- content_hash has sha256: prefix
- id follows evidence:seed: prefix convention

Empty or missing seeds.jsonl → OK (AC-EV-7).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_FIELDS = ("id", "kind", "uri", "retrieved_at", "content_hash", "chunk", "md_path", "tool_version")
HASH_RE = re.compile(r'^sha256:[0-9a-f]{64}$')
ID_RE = re.compile(r'^evidence:seed:.+$')


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="validate_seeds")
    p.add_argument("--target", required=True)
    return p.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    target = Path(args.target).resolve()
    seeds_path = target / "evidence" / "seeds.jsonl"

    if not seeds_path.exists():
        print(f"OK: seeds.jsonl not present at {target} (0 seeds — acceptable)")
        return 0

    text = seeds_path.read_text(encoding="utf-8")
    if not text.strip():
        print(f"OK: seeds.jsonl is empty at {target}")
        return 0

    failures: list[str] = []
    count = 0

    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            failures.append(f"line {lineno}: invalid JSON: {exc}")
            continue
        count += 1

        # Required fields
        for field in REQUIRED_FIELDS:
            if field not in obj:
                failures.append(f"line {lineno} ({obj.get('id','?')}): missing field '{field}'")

        # id format
        seed_id = obj.get("id", "")
        if seed_id and not ID_RE.match(seed_id):
            failures.append(f"line {lineno}: id does not match 'evidence:seed:...' pattern: {seed_id!r}")

        # content_hash format
        ch = obj.get("content_hash", "")
        if ch and not HASH_RE.match(ch):
            failures.append(f"line {lineno} ({seed_id}): invalid content_hash: {ch!r}")

        # chunk sub-fields
        chunk = obj.get("chunk", {})
        if not isinstance(chunk, dict):
            failures.append(f"line {lineno} ({seed_id}): 'chunk' must be an object")
        else:
            for sub in ("index", "total", "char_start", "char_end", "text_preview"):
                if sub not in chunk:
                    failures.append(f"line {lineno} ({seed_id}): chunk.{sub} missing")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        print(f"FAIL: {len(failures)} issue(s) found in {count} seeds", file=sys.stderr)
        return 1

    print(f"OK: {count} seed(s) pass L0 static validation at {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
