#!/usr/bin/env python3
"""List seeds from evidence/seeds.jsonl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as _layout_mod  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="list_seeds")
    p.add_argument("--target", default=".", help="KB root path")
    p.add_argument("--format", choices=["table", "json", "ids"], default="table")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    target = Path(args.target).resolve()
    seeds_path = _layout_mod.resolve_layout(target)["seeds_path"]

    if not seeds_path.exists():
        print("(no seeds.jsonl found)")
        return 0

    seeds: list[dict] = []
    with seeds_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                seeds.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if not seeds:
        print("(empty seeds.jsonl — 0 seeds)")
        return 0

    fmt = args.format
    if fmt == "json":
        json.dump(seeds, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    elif fmt == "ids":
        for s in seeds:
            print(s.get("id", ""))
    else:
        # Table
        print(f"{'ID':<45} {'KIND':<5} {'STATUS':<12} {'HASH':<16}")
        print("-" * 85)
        for s in seeds:
            sid = s.get("id", "")[:44]
            kind = s.get("kind", "")[:4]
            status = s.get("status", "")[:11]
            ch = s.get("content_hash", "")
            ch_short = ch[:16] if ch else ""
            print(f"{sid:<45} {kind:<5} {status:<12} {ch_short}")
        print(f"\nTotal: {len(seeds)} seed(s)")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
