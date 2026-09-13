#!/usr/bin/env python3
"""Generate ontology statistics from canonical Turtle."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from ttl_state import ontology_state, seed_records


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="analyze")
    parser.add_argument("--target", required=True)
    parser.add_argument("--domain", "--cluster", dest="domain")
    parser.add_argument("--run-id")
    return parser.parse_args(argv)


def build_report(target: Path, domain: str | None, state: dict) -> str:
    counts = state["counts"]
    lines = [
        '<!-- skb:generated:file skill="skb-maintain" version="1.1.0" -->',
        f"# Maintain Analysis — {target.name}",
        "",
        f"- domain: {domain or 'all'}",
        f"- asserted Turtle files: {len(state['paths'])}",
        f"- triples: {len(state['graph'])}",
        f"- classes: {counts.get('classes', 0)}",
        f"- SKOS concepts: {counts.get('concepts', 0)}",
        f"- object properties: {counts.get('object_properties', 0)}",
        f"- datatype properties: {counts.get('datatype_properties', 0)}",
        f"- individuals: {counts.get('individuals', 0)}",
        f"- semantic relations: {len(state['relations'])}",
        f"- status distribution: {state['statuses']}",
        f"- evidence coverage: {state['evidence_coverage']:.3f}",
        f"- relation density: {state['relation_density']:.3f}",
        f"- semantic orphans: {len(state['orphan_terms'])}",
        f"- TTL validation failures: {len(state['failures'])}",
        f"- evidence seeds: {len(seed_records(target))}",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    target = Path(args.target).resolve()
    identifier = args.run_id or dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    state = ontology_state(target, args.domain)
    report = build_report(target, args.domain, state)
    directory = target / "harness" / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"maintain-analysis-{identifier}.md"
    path.write_text(report, encoding="utf-8")
    print(report)
    print(f"[analyze] Report saved: {path}", file=sys.stderr)
    return 0 if not state["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
