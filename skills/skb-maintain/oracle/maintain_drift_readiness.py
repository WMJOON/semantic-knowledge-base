#!/usr/bin/env python3
"""Score TTL graph validity, provenance coverage, connectivity, and hub state."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from ttl_state import ontology_state  # noqa: E402

LOCKED_RE = re.compile(r"^\s*locked\s*:\s*true\s*$", re.MULTILINE)


def evaluate(target: Path, domain: str | None = None) -> dict:
    state = ontology_state(target, domain)
    hub = target / "canonical_root_hub.yaml"
    hub_ok = hub.exists() and bool(LOCKED_RE.search(hub.read_text("utf-8")))
    breakdown = {
        "ttl_graph_valid": 0.40 if not state["failures"] else 0.0,
        "semantic_orphan_zero": 0.20 if not state["orphan_terms"] else 0.0,
        "evidence_coverage_ok": 0.20 if state["evidence_coverage"] >= 0.80 else 0.0,
        "relation_density_ok": 0.10 if not state["declared"] or state["relation_density"] >= 0.5 else 0.0,
        "hub_ok": 0.10 if hub_ok else 0.0,
    }
    score = round(sum(breakdown.values()), 3)
    return {
        "score": score,
        "gate": "pass" if score >= 0.85 else "warn" if score >= 0.70 else "fail",
        "breakdown": breakdown,
        "metrics": {
            "ttl_validation_failures": len(state["failures"]),
            "semantic_orphans": len(state["orphan_terms"]),
            "evidence_coverage": state["evidence_coverage"],
            "relation_density": state["relation_density"],
            "canonical_hub_locked": hub_ok,
        },
    }


def emit(target: Path, identifier: str, result: dict) -> None:
    directory = target / "harness" / "trajectory"
    directory.mkdir(parents=True, exist_ok=True)
    event = {
        "run_id": identifier,
        "ts": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "event_type": "oracle_evaluation",
        "oracle": "maintain_drift_readiness",
        **result,
    }
    path = directory / f"run-{identifier}.jsonl"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (json.dumps(event, ensure_ascii=False) + "\n").encode())
    finally:
        os.close(fd)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--domain")
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    result = evaluate(args.target.resolve(), args.domain)
    if args.run_id:
        emit(args.target.resolve(), args.run_id, result)
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if result["gate"] == "pass" else 1 if result["gate"] == "warn" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
