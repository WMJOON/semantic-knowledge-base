#!/usr/bin/env python3
"""SPEC §8.1: root writable + required directories."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REQUIRED = (
    "ontology/system/semantic",
    "ontology/system/kinetic",
    "ontology/system/dynamic",
    "ontology/explain/concept",
    "ontology/explain/instance",
    "evidence/md",
    "evidence/graphify",
    "record-archive/registry",
    "record-archive/runtime",
    "record-archive/events",
    "record-archive/derived",
    "record-archive/snapshots",
    "record-archive/schema",
    "planning/research", "planning/ontology",
    "report/paper",
    "docs", "docs/guideline",
    "agent-context/index",
    "agent-context/workflow/evidence",
    "agent-context/workflow/ontology",
    "agent-context/workflow/maintain",
    "agent-context/workflow/explorer",
    "agent-context/work-memory/auditlog",
    "agent-context/work-memory/worklog",
    "agent-context/work-memory/track-record",
    "agent-context/work-memory/insight-record",
    "harness/tiers/L0_static",
    "harness/tiers/L1_fixture",
    "harness/tiers/L2_integration",
    "harness/tiers/L3_eval",
    "harness/fixtures",
    "harness/trajectory",
    "harness/reports",
    "harness/oracle",
    ".msm-context",
    ".msm-context/active",
    ".msm-context/archive",
    ".claude/skills", ".claude/hooks",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    args = ap.parse_args()
    target = Path(args.target).resolve()
    if not target.exists() or not os.access(target, os.W_OK):
        print(f"FAIL: target not writable: {target}", file=sys.stderr)
        return 1
    missing = [d for d in REQUIRED if not (target / d).is_dir()]
    if missing:
        print("FAIL: missing required directories:", file=sys.stderr)
        for d in missing:
            print(f"  - {d}", file=sys.stderr)
        return 1
    print(f"OK: {len(REQUIRED)} required directories present at {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
