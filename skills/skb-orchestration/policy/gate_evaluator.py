#!/usr/bin/env python3
"""Gate evaluator.

SPEC §6.2: reads the harness `governance_measurement` event, applies the
resolved threshold table, emits a single `gate_decision` event into the
orchestration mirror file.

Caller-facing exit codes (SPEC §9.4):
  0   passed
  100 HITL pending (always_hitl or layer-2 escalate)
  101 gate fail, retry budget exhausted
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_HOME / "router"))
sys.path.insert(0, str(SKILL_HOME / "policy"))

import mirror_writer as mw  # noqa: E402
import threshold_resolver as tr  # noqa: E402


def _read_measurement(target: Path, run_id: str) -> dict | None:
    traj = target / "harness" / "trajectory" / f"run-{run_id}.jsonl"
    if not traj.exists():
        return None
    for line in traj.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("event_type") == "governance_measurement":
            return ev
    return None


def _evaluate(measurement: dict, thresholds: dict) -> dict:
    axes: dict = {}
    violated: list[str] = []

    # Non-determinism (only meaningful when sample_n >= 2 — otherwise auto-pass)
    nd = float(measurement.get("non_determinism", 0.0))
    nd_max = float((thresholds.get("non_determinism") or {}).get("max", 0.15))
    nd_pass = nd <= nd_max
    axes["non_determinism"] = {"value": nd, "threshold_max": nd_max, "pass": nd_pass}
    if not nd_pass:
        violated.append("non_determinism")

    # Trajectory
    traj_complete = bool(measurement.get("trajectory_complete", False))
    axes["trajectory"] = {"complete": traj_complete, "pass": traj_complete}
    if not traj_complete:
        violated.append("trajectory")

    # Oracle
    score = float(measurement.get("oracle_score", 0.0))
    min_score = float((thresholds.get("oracle") or {}).get("min_score", 0.85))
    oracle_pass = score >= min_score
    axes["oracle"] = {"score": score, "threshold_min": min_score, "pass": oracle_pass}
    if not oracle_pass:
        violated.append("oracle")

    # Cost
    cost = measurement.get("cost") or {}
    mode = cost.get("mode", "fallback")
    budget_block = (thresholds.get("cost") or {}).get(f"{mode}_mode") or {}
    tokens = int(cost.get("tokens", 0) or 0)
    seconds = float(cost.get("seconds", 0) or 0)
    power_wh = float(cost.get("power_wh", 0) or 0)
    breach = False
    if tokens > int(budget_block.get("tokens_max", 10**9) or 10**9):
        breach = True
    if seconds > float(budget_block.get("seconds_max", 1e12) or 1e12):
        breach = True
    if mode == "full" and power_wh > float(budget_block.get("power_wh_max", 1e12) or 1e12):
        breach = True
    axes["cost"] = {
        "tokens": tokens, "seconds": seconds, "power_wh": power_wh,
        "budget_breach": breach, "pass": not breach,
    }
    if breach:
        violated.append("cost")

    # HITL — required > acked means a still-pending request
    hitl = measurement.get("hitl") or {}
    required = bool(hitl.get("required", False))
    requested = int(hitl.get("requested", 0) or 0)
    acked = int(hitl.get("acked", 0) or 0)
    pending = required and acked < requested
    axes["hitl"] = {"required": required, "requested": requested, "acked": acked,
                    "pending": pending, "pass": not pending}
    if pending:
        violated.append("hitl")

    return {"axes": axes, "violated": violated}


def _next_action(violated: list[str]) -> str:
    if not violated:
        return "proceed"
    # cost / non_determinism / oracle / trajectory failures escalate HITL.
    if "hitl" in violated:
        return "escalate_hitl"
    if any(v in violated for v in ("non_determinism", "oracle", "cost", "trajectory")):
        return "escalate_hitl"
    return "abort"


# Axis → SPEC §7.2 observability trigger reason mapping
AXIS_TO_REASON = {
    "non_determinism": "non_determinism_high",
    "oracle": "oracle_below_threshold",
    "cost": "cost_budget_exceeded",
    "trajectory": "trajectory_incomplete",
    "hitl": "hitl_pending_ack",
}


def evaluate_and_emit(target: Path, run_id: str,
                      workflow_id: str | None = None,
                      category: str | None = None) -> int:
    measurement = _read_measurement(target, run_id)
    if measurement is None:
        mw.emit(target, run_id, {"event_type": "gate_decision", "passed": False,
                                 "axes": {}, "violated_axes": ["no_measurement"],
                                 "next_action": "abort"})
        return 101
    thresholds = tr.resolve(workflow_id=workflow_id, category=category)
    result = _evaluate(measurement, thresholds)
    passed = not result["violated"]
    next_action = _next_action(result["violated"])

    # SPEC §7.3: emit a hitl_request per violated axis BEFORE the gate_decision
    # whenever escalation is required. Consumers (hitl-ack, UIs) bind to these
    # events; without them the audit trail is incomplete.
    if next_action == "escalate_hitl":
        for axis in result["violated"]:
            reason = AXIS_TO_REASON.get(axis, axis)
            axis_data = result["axes"].get(axis, {})
            mw.emit(target, run_id, {
                "event_type": "hitl_request",
                "requires_manual_confirmation": True,
                "reason": reason,
                "axis": axis,
                "target": workflow_id or "run",
                "details": axis_data,
                "proposed_action": "review and hitl-ack or abort",
            })

    event = {
        "event_type": "gate_decision",
        "passed": passed,
        "axes": result["axes"],
        "violated_axes": result["violated"],
        "next_action": next_action,
        "thresholds_resolved_from": {
            "workflow_id": workflow_id,
            "category": category,
        },
    }
    mw.emit(target, run_id, event)
    if passed:
        return 0
    return 100 if next_action == "escalate_hitl" else 101


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="gate_evaluator")
    p.add_argument("--target", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--workflow-id", default=None)
    p.add_argument("--category", default=None)
    args = p.parse_args(argv)
    target = Path(args.target).resolve()
    return evaluate_and_emit(target, args.run_id, workflow_id=args.workflow_id, category=args.category)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
