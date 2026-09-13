#!/usr/bin/env python3
"""SPEC §8.2 readiness score for a generated MSM repo."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

WEIGHTS = {
    "five_layer_directories": 0.20,
    "canonical_hub_valid": 0.20,
    "workflow_templates_valid": 0.15,
    "memory_harness_skeleton_valid": 0.15,
    "docs_index_present": 0.10,
    "skill_links_valid_or_skipped": 0.10,
    "no_unresolved_conflicts": 0.10,
}

REQUIRED_TOP_DIRS = ("ontology", "evidence", "record-archive", "agent-context", "harness", "docs")
REQUIRED_HUB_KEYS = ("version:", "locked:", "domains:", "scan:", "sync:")
REQUIRED_SYNC = ("structural_ssot: ttl", "projection_target: md", "auto_apply_md_to_ttl: false")
WORKFLOW_REQUIRED = (
    "version:", "id:", "category:", "kind:", "mode:",
    "inputs:", "outputs:", "runtime:", "governance:",
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="score_readiness")
    p.add_argument("--target", required=True)
    p.add_argument("--run-id", default=None)
    return p.parse_args(argv)


def score(target: Path) -> dict:
    breakdown: dict[str, bool] = {}

    breakdown["five_layer_directories"] = all((target / d).is_dir() for d in REQUIRED_TOP_DIRS)

    hub = target / "canonical_root_hub.yaml"
    hub_ok = False
    if hub.exists():
        text = hub.read_text(encoding="utf-8")
        hub_ok = all(k in text for k in REQUIRED_HUB_KEYS) and all(s in text for s in REQUIRED_SYNC)
    breakdown["canonical_hub_valid"] = hub_ok

    semantic_root = target / "ontology" / "system" / "semantic"
    if semantic_root.exists() and any(semantic_root.rglob("*.ttl")):
        breakdown["five_layer_directories"] = breakdown["five_layer_directories"] and True

    workflow_root = target / "agent-context" / "workflow"
    index = workflow_root / "index.yaml"
    wfs_ok = index.exists() and "workflows:" in index.read_text(encoding="utf-8")
    if wfs_ok:
        for sub in workflow_root.rglob("*.yaml"):
            if sub.name == "index.yaml":
                continue
            wfs_ok = wfs_ok and all(k in sub.read_text(encoding="utf-8") for k in WORKFLOW_REQUIRED)
    breakdown["workflow_templates_valid"] = wfs_ok

    breakdown["memory_harness_skeleton_valid"] = (
        (target / "agent-context" / "work-memory" / "worklog").is_dir()
        and (target / "agent-context" / "work-memory" / "index.md").exists()
        and (target / "harness" / "run.sh").exists()
        and (target / "harness" / "trajectory").is_dir()
    )

    breakdown["docs_index_present"] = (target / "docs" / "index.md").exists()

    # skill links: home dir not touched by default, so credit when nothing claimed.
    skill_link_marker = target / ".claude" / "skills"
    breakdown["skill_links_valid_or_skipped"] = skill_link_marker.is_dir()

    # Unresolved conflicts: trajectory contains hitl_request without follow-up.
    breakdown["no_unresolved_conflicts"] = True
    traj_dir = target / "harness" / "trajectory"
    if traj_dir.is_dir():
        for jf in traj_dir.glob("run-*.jsonl"):
            text = jf.read_text(encoding="utf-8", errors="ignore")
            if "hitl_request" in text and "apply_partial" not in text and "hitl_ack" not in text:
                # heuristic: legitimate HITL ack would emit apply_partial or hitl_ack
                if "canonical_root_hub_locked_change" in text:
                    breakdown["no_unresolved_conflicts"] = False
                    break

    total = sum(WEIGHTS[k] for k, v in breakdown.items() if v)
    gate = "pass" if total >= 0.85 else "warn" if total >= 0.70 else "fail"
    return {"score": round(total, 3), "gate": gate, "breakdown": breakdown}


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    target = Path(args.target).resolve()
    result = score(target)
    run_id = args.run_id or _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    event = {
        "run_id": run_id,
        "event_type": "repository_setup_readiness",
        "score": result["score"],
        "gate_passed": result["gate"] == "pass",
        "gate": result["gate"],
        "breakdown": result["breakdown"],
    }
    traj_dir = target / "harness" / "trajectory"
    traj_dir.mkdir(parents=True, exist_ok=True)
    (traj_dir / f"run-{run_id}.jsonl").open("a", encoding="utf-8").write(
        json.dumps(event, ensure_ascii=False) + "\n"
    )
    json.dump(event, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if result["gate"] == "pass" else 1 if result["gate"] == "warn" else 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
