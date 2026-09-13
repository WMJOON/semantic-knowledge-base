#!/usr/bin/env python3
"""Scan canonical Turtle for validation failures and semantic orphans."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from ttl_state import ontology_state, seed_records


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="scan")
    parser.add_argument("--target", required=True)
    parser.add_argument("--domain", "--cluster", dest="domain")
    parser.add_argument("--kind", default="all", choices=["drift", "orphan", "eval", "all"])
    parser.add_argument("--run-id")
    return parser.parse_args(argv)


def run_id(value: str | None) -> str:
    return value or dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def seed_orphans(target: Path) -> list[dict]:
    referenced = {
        str(record.get("md_path", ""))
        for record in seed_records(target)
        if record.get("md_path")
    }
    findings: list[dict] = []
    for root in (target / "evidence" / "md", target / "evidence" / "chunk"):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            relative = str(path.relative_to(target))
            if relative not in referenced:
                findings.append({"kind": "seed_orphan", "path": relative})
    return findings


def build_plan(target: Path, domain: str | None, kind: str, identifier: str) -> dict:
    state = ontology_state(target, domain)
    selected = ["drift", "orphan", "eval"] if kind == "all" else [kind]
    findings: dict[str, list[dict]] = {}
    if "drift" in selected:
        findings["drift"] = [
            {"kind": "ttl_validation", "detail": failure}
            for failure in state["failures"]
        ]
    if "orphan" in selected:
        findings["orphan"] = [
            {"kind": "semantic_orphan", "iri": str(term)}
            for term in state["orphan_terms"]
        ] + seed_orphans(target)
    if "eval" in selected:
        findings["eval"] = [{
            "domain": domain or "all",
            **state["counts"],
            "relations": len(state["relations"]),
            "status_dist": state["statuses"],
            "evidence_coverage": state["evidence_coverage"],
            "relation_density": state["relation_density"],
        }]
    hitl = [
        {"reason": item["kind"], **item}
        for group in ("drift", "orphan")
        for item in findings.get(group, [])
    ]
    return {
        "plan_id": f"maintain-{identifier}",
        "target": str(target),
        "domain": domain,
        "scans_performed": selected,
        "findings": findings,
        "auto_fixes": [],
        "hitl_required": hitl,
    }


def emit_trajectory(target: Path, identifier: str, plan: dict) -> None:
    directory = target / "harness" / "trajectory"
    directory.mkdir(parents=True, exist_ok=True)
    event = {
        "run_id": identifier,
        "ts": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "event_type": "scan_complete",
        "plan_id": plan["plan_id"],
        "drift_count": len(plan["findings"].get("drift", [])),
        "orphan_count": len(plan["findings"].get("orphan", [])),
        "auto_fixes_count": 0,
    }
    path = directory / f"run-{identifier}.jsonl"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (json.dumps(event, ensure_ascii=False) + "\n").encode())
    finally:
        os.close(fd)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    target = Path(args.target).resolve()
    identifier = run_id(args.run_id)
    plan = build_plan(target, args.domain, args.kind, identifier)
    json.dump(plan, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    emit_trajectory(target, identifier, plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
