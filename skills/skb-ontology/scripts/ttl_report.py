#!/usr/bin/env python3
"""Read-only reports over canonical Turtle: semantic orphans and graph statistics.

  ttl_report.py orphans --target KB [--domain D] [--json]   accepted/stable 용어 중 어떤 의미 관계에도 없는 용어
  ttl_report.py stats   --target KB [--domain D] [--json] [--out FILE]   개수, status 분포, evidence 커버리지, 관계 밀도

둘 다 정본 TTL 을 수정하지 않는다. 용어 고아는 정본 문제가 아니라 점검 대상이라 종료 코드는 항상 0 이고
(TTL 검증 실패가 있으면 1), 판정은 사람이 한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ttl_state import ontology_state, seed_records  # noqa: E402


def stats_text(target: Path, domain: str | None, state: dict) -> str:
    c = state["counts"]
    return "\n".join([
        f"# Ontology statistics — {target.name}", "",
        f"- domain: {domain or 'all'}",
        f"- asserted Turtle files: {len(state['paths'])}",
        f"- triples: {len(state['graph'])}",
        f"- classes: {c.get('classes', 0)}",
        f"- SKOS concepts: {c.get('concepts', 0)}",
        f"- object properties: {c.get('object_properties', 0)}",
        f"- datatype properties: {c.get('datatype_properties', 0)}",
        f"- individuals: {c.get('individuals', 0)}",
        f"- semantic relations: {len(state['relations'])}",
        f"- status distribution: {state['statuses']}",
        f"- evidence coverage: {state['evidence_coverage']:.3f}",
        f"- relation density: {state['relation_density']:.3f}",
        f"- semantic orphans: {len(state['orphan_terms'])}",
        f"- TTL validation failures: {len(state['failures'])}",
        f"- evidence seeds: {len(seed_records(target))}", ""])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ttl_report", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("orphans", "stats"):
        p = sub.add_parser(name)
        p.add_argument("--target", required=True, type=Path)
        p.add_argument("--domain")
        p.add_argument("--json", action="store_true")
        if name == "stats":
            p.add_argument("--out", type=Path, help="Markdown 으로도 저장")
    a = ap.parse_args(argv)
    target = a.target.resolve()
    state = ontology_state(target, a.domain)
    if a.cmd == "orphans":
        orphans = [str(t) for t in state["orphan_terms"]]
        if a.json:
            print(json.dumps({"orphans": orphans, "count": len(orphans)}, ensure_ascii=False, indent=1))
        else:
            print(f"semantic orphans: {len(orphans)}")
            for t in orphans:
                print(" ", t)
    else:
        text = stats_text(target, a.domain, state)
        if a.out:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text(text, encoding="utf-8")
        if a.json:
            print(json.dumps({"counts": state["counts"], "statuses": state["statuses"], "relations": len(state["relations"]),
                              "evidence_coverage": state["evidence_coverage"], "relation_density": state["relation_density"],
                              "orphans": len(state["orphan_terms"]), "ttl_failures": len(state["failures"]),
                              "seeds": len(seed_records(target))}, ensure_ascii=False, indent=1))
        else:
            print(text)
    return 1 if state["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
