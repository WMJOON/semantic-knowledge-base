"""Trigger → workflow_id resolver.

SPEC §4.1 — match a free-form intent against router-trigger-map.yaml.
Algorithm: longest matched-keyword wins; ties broken by priority (higher first).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _yaml_lite as yaml  # noqa: E402

REF_MAP = SCRIPT_DIR.parents[0] / "references" / "router-trigger-map.yaml"


def _score(intent: str, trig: dict) -> tuple[int, int, list[str]]:
    """Return (matched_chars, priority, matched_keywords)."""
    intent_l = intent.lower()
    when = trig.get("when", {}) or {}
    matched: list[str] = []
    chars = 0
    for kw in when.get("keywords", []) or []:
        if kw.lower() in intent_l:
            matched.append(kw)
            chars += len(kw)
    for alias in when.get("legacy_aliases", []) or []:
        if alias.lower() in intent_l:
            matched.append(alias)
            chars += len(alias)
    for it in when.get("intents", []) or []:
        if it.lower() in intent_l:
            matched.append(f"intent:{it}")
            chars += len(it)
    priority = int(trig.get("priority", 0) or 0)
    return chars, priority, matched


def match(intent: str, trigger_map_path: Path = REF_MAP) -> dict | None:
    data = yaml.load(trigger_map_path)
    triggers = data.get("triggers", []) or []
    best: dict | None = None
    best_key = (-1, -1)
    best_matched: list[str] = []
    for trig in triggers:
        chars, prio, matched = _score(intent, trig)
        if chars <= 0:
            continue
        key = (chars, prio)
        if key > best_key:
            best = trig
            best_key = key
            best_matched = matched
    if best is None:
        return None
    return {
        "trigger_id": best["id"],
        "matched_keywords": best_matched,
        "priority": int(best.get("priority", 0) or 0),
        "route": best.get("route", {}),
        "legacy_aliases": best.get("when", {}).get("legacy_aliases", []) or [],
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="match_trigger")
    p.add_argument("--intent", required=True)
    p.add_argument("--map", default=str(REF_MAP))
    args = p.parse_args(argv)
    result = match(args.intent, Path(args.map))
    if result is None:
        print("{}")
        return 1
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
