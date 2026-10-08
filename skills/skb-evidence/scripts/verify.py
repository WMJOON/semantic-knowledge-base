#!/usr/bin/env python3
"""Verify seeds.jsonl: check md_path files exist + content_hash format.

Exit 0 if all seeds pass; exit 1 if any fail.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as _layout_mod  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="verify")
    p.add_argument("--target", default=".", help="KB root path")
    p.add_argument("--id", default=None, help="Verify single seed by id")
    p.add_argument("--orphans", action="store_true", help="Also report evidence/md notes that no seed references (the reverse direction of 'md_path not found')")
    p.add_argument("--strict", action="store_true", help="Treat --orphans findings as failures instead of warnings")
    return p.parse_args(argv)


def orphan_md_notes(seeds: list[dict], target: Path) -> list[str]:
    """evidence/md notes (KB-relative) that no seed's md_path points to."""
    target = Path(target).resolve()  # resolve_layout returns resolved absolute paths (macOS /var -> /private/var)
    referenced = {str(s.get("md_path")) for s in seeds if s.get("md_path")}
    md_dir = _layout_mod.resolve_layout(target)["evidence_md_dir"]
    if not md_dir.exists():
        return []
    return sorted(str(p.relative_to(target)) for p in md_dir.rglob("*.md") if str(p.relative_to(target)) not in referenced)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    target = Path(args.target).resolve()
    seeds_path = _layout_mod.resolve_layout(target)["seeds_path"]

    if not seeds_path.exists():
        print("OK: seeds.jsonl not found (0 seeds)")
        return 0

    seeds: list[dict] = []
    with seeds_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                seeds.append(obj)
            except json.JSONDecodeError as exc:
                print(f"ERROR: invalid JSON line: {exc}", file=sys.stderr)
                return 1

    if not seeds:
        print("OK: seeds.jsonl empty (0 seeds)")
        return 0

    if args.id:
        seeds = [s for s in seeds if s.get("id") == args.id]
        if not seeds:
            print(f"ERROR: seed {args.id} not found", file=sys.stderr)
            return 1

    failures: list[str] = []
    hash_re = re.compile(r'^sha256:[0-9a-f]{64}$')

    for seed in seeds:
        sid = seed.get("id", "<unknown>")

        # Check content_hash format
        ch = seed.get("content_hash", "")
        if not hash_re.match(ch):
            failures.append(f"{sid}: invalid content_hash: {ch!r}")

        # Check md_path exists
        md_rel = seed.get("md_path", "")
        if md_rel:
            md_abs = target / md_rel
            if not md_abs.exists():
                failures.append(f"{sid}: md_path not found: {md_rel}")
        else:
            failures.append(f"{sid}: missing md_path field")

    if args.orphans and not args.id:
        orphans = orphan_md_notes(seeds, target)
        if orphans:
            shown = orphans[:20]
            msg = f"{len(orphans)} md note(s) not referenced by seeds.jsonl" + (
                f" (first {len(shown)}: {', '.join(shown)})" if len(orphans) > len(shown) else f": {', '.join(shown)}")
            if args.strict:
                failures.append(msg)
            else:
                print(f"WARN: {msg}", file=sys.stderr)

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        print(f"\n{len(failures)} verification failure(s) in {len(seeds)} seed(s)", file=sys.stderr)
        return 1

    print(f"OK: {len(seeds)} seed(s) verified")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
