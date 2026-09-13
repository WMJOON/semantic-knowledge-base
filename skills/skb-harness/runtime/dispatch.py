#!/usr/bin/env python3
"""skb-harness run dispatcher.

Implements skb-harness-SPEC §6, §7 (run.sh), §8 (trajectory), §9 (5-axis),
§10 (oracle), §11 (retry). The bash entrypoint is `run.sh`, which is a thin
wrapper around this module.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from cost_detector import detect_mode, estimate_power_wh  # noqa: E402
from manifest_writer import (  # noqa: E402
    append_decision,
    finalize_outputs,
    write_manifest,
)
from oracle_runner import run_oracle  # noqa: E402
from retry_controller import is_retry_safe, should_retry  # noqa: E402
from trajectory_writer import emit, read_events  # noqa: E402
from workflow_parser import parse as parse_workflow  # noqa: E402


HUB_LOCK = ".msm-context/active/.hub-write.lock"


def _now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_run_id(target: Path | None = None) -> str:
    """ISO 8601 basic UTC + 4-hex suffix on collision (SPEC §5.1)."""
    import secrets

    base = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if target is None:
        return base
    traj = target / "harness" / "trajectory"
    slot = target / ".msm-context" / "active"
    candidate = base
    for _ in range(8):
        if not (traj / f"run-{candidate}.jsonl").exists() and not (slot / candidate).exists():
            return candidate
        candidate = f"{base}-{secrets.token_hex(2)}"
    return candidate


def _common_fields(args: argparse.Namespace, workflow_id: str | None) -> dict[str, Any]:
    return {
        "skill": args.skill,
        "workflow_id": workflow_id,
        "tier": args.tier,
        "mode": args.mode,
        "parent_run_id": args.parent_run_id,
    }


def _locate_skill(name: str) -> Path | None:
    """Resolve a skill module directory.

    Priority (sibling first — version-matched dev tree wins over potentially
    stale globals; in production the install puts the same version at both
    spots):
      1) MSM_SKILL_<UPPER_SNAKE>_HOME env var
      2) Sibling of skb-harness in the same skills/ directory
      3) ~/.claude/skills/<name>
    """
    env_key = f"MSM_SKILL_{name.replace('-', '_').upper()}_HOME"
    override = os.environ.get(env_key)
    if override and Path(override).exists():
        return Path(override).resolve()
    sibling = SCRIPT_DIR.parents[1] / name
    if sibling.exists():
        return sibling.resolve()
    home = Path.home() / ".skill-modules" / "msm-skills" / name
    if home.exists():
        return home.resolve()
    return None


def _exec_skill(skill_home: Path, skill: str, target: Path, mode: str) -> tuple[int, dict[str, Any]]:
    """Invoke a skill's primary entrypoint and collect a tiny output summary."""
    # Convention: each skill exposes `scripts/<name>` (bash CLI) or `harness/run.sh`.
    # skb-repository-setup uses `scripts/msm`; others may differ.
    started = time.monotonic()
    outputs: dict[str, Any] = {}
    if skill == "skb-repository-setup":
        cli = skill_home / "scripts" / "msm"
        if cli.exists():
            cmd = [str(cli), "init", "--target", str(target)]
            if mode == "validate-only":
                cmd.append("--validate-only")
            elif mode == "apply":
                cmd += ["--apply", "--yes"]
            else:
                cmd.append("--dry-run")
            rc = subprocess.run(cmd, check=False).returncode
            outputs["entrypoint"] = str(cli)
        else:
            return (127, {"error": "skb-repository-setup CLI not found"})
    else:
        run_sh = skill_home / "harness" / "run.sh"
        if run_sh.exists():
            rc = subprocess.run(
                [str(run_sh), "--skill", skill, "--tier", "L0", "--mode", mode, "--target", str(target)],
                check=False,
            ).returncode
            outputs["entrypoint"] = str(run_sh)
        else:
            return (127, {"error": f"{skill} has no recognised entrypoint"})
    outputs["wall_seconds"] = round(time.monotonic() - started, 3)
    return (rc, outputs)


def _exec_workflow(args: argparse.Namespace, wf: dict[str, Any], target: Path, run_id: str) -> tuple[int, dict[str, Any]]:
    common = _common_fields(args, wf.get("id"))
    max_retry = int(wf.get("governance", {}).get("max_retry", 1) or 1)
    outputs: dict[str, Any] = {}

    steps: list[dict[str, Any]]
    if wf.get("kind") == "pipeline":
        steps = wf.get("pipeline") or []
    else:
        steps = [{"step_id": "step", "tool": wf.get("tool"), "action": "default"}]

    overall_rc = 0
    for step in steps:
        step_id = step.get("step_id") or step.get("tool") or "step"
        tool = step.get("tool")
        action = step.get("action", "default")
        attempt = 0
        last_rc = 0
        while True:
            attempt += 1
            emit(target, run_id, {
                "event_type": "step_started",
                "step_id": step_id,
                "tool": tool,
                "action": action,
                "attempt": attempt,
            }, common)
            if not tool:
                emit(target, run_id, {
                    "event_type": "step_aborted",
                    "step_id": step_id,
                    "reason": "missing_tool_field",
                }, common)
                overall_rc = 1
                break
            skill_home = _locate_skill(tool)
            if skill_home is None:
                # Soft-pass: in Phase 3 most domain skills aren't built yet, so
                # we mark the step aborted and move on without a duplicate
                # `step_finished` event (consumers would otherwise double-count).
                emit(target, run_id, {
                    "event_type": "step_aborted",
                    "step_id": step_id,
                    "reason": "skill_not_installed",
                    "skill": tool,
                    "attempt": attempt,
                }, common)
                break
            rc, step_out = _exec_skill(skill_home, tool, target, args.mode)
            outputs[step_id] = step_out
            emit(target, run_id, {
                "event_type": "step_finished",
                "step_id": step_id,
                "exit_code": rc,
                "attempt": attempt,
                "outputs_delta": step_out,
            }, common)
            last_rc = rc
            if rc == 0:
                break
            if should_retry(rc, attempt, max_retry):
                # Backoff is intentionally tiny in tests; orchestration may
                # override in future.
                time.sleep(min(0.1 * attempt, 1.0))
                continue
            if is_retry_safe(rc):
                # Exhausted retries on retry-safe code → HITL
                emit(target, run_id, {
                    "event_type": "hitl_request",
                    "reason": "retry_budget_exhausted",
                    "target": step_id,
                    "proposed_action": "review_and_resume",
                    "requires_manual_confirmation": True,
                }, common)
            overall_rc = rc
            break
        if overall_rc != 0:
            break

    return overall_rc, outputs


def _aggregate_cost(target: Path, run_id: str, wall_seconds: float, cost_mode: str) -> dict[str, Any]:
    tokens = 0
    seconds = 0.0
    power_wh = 0.0
    for ev in read_events(target, run_id):
        if ev.get("event_type") == "cost_increment":
            tokens += int(ev.get("tokens_delta", 0) or 0)
            seconds += float(ev.get("seconds_delta", 0) or 0)
            power_wh += float(ev.get("power_wh_delta", 0) or 0)
    # wall_seconds fallback if no skill emitted cost_increment
    if seconds <= 0:
        seconds = round(wall_seconds, 3)
    # Power can be computed lazily if not provided
    if cost_mode == "full" and power_wh == 0 and tokens > 0:
        power_wh = estimate_power_wh(None, tokens, mode="full")
    elif cost_mode == "fallback":
        power_wh = 0.0
    return {"mode": cost_mode, "tokens": tokens, "seconds": round(seconds, 3), "power_wh": round(power_wh, 6)}


def _trajectory_complete(target: Path, run_id: str) -> tuple[bool, list[dict[str, Any]]]:
    starts: dict[str, int] = {}
    ends: dict[str, int] = {}
    for ev in read_events(target, run_id):
        et = ev.get("event_type")
        sid = ev.get("step_id")
        if et == "step_started" and sid:
            starts[sid] = starts.get(sid, 0) + 1
        elif et in ("step_finished", "step_aborted") and sid:
            ends[sid] = ends.get(sid, 0) + 1
    gaps = [{"step_id": sid, "starts": n, "ends": ends.get(sid, 0)} for sid, n in starts.items() if ends.get(sid, 0) < n]
    return (not gaps, gaps)


def _hitl_counts(target: Path, run_id: str) -> dict[str, int]:
    req = ack = 0
    for ev in read_events(target, run_id):
        et = ev.get("event_type")
        if et == "hitl_request":
            req += 1
        elif et == "hitl_ack":
            ack += 1
    return {"required": req > 0, "requested": req, "acked": ack}


def _write_work_log(target: Path, run_id: str, summary: dict[str, Any]) -> Path:
    log_dir = target / "memory" / "task-context" / "work-log"
    log_dir.mkdir(parents=True, exist_ok=True)
    out = log_dir / f"{run_id}.md"
    cost = summary["cost"]
    out.write_text(
        "---\n"
        f"run_id: {run_id}\n"
        f"workflow_id: {summary.get('workflow_id')}\n"
        f"skill: {summary.get('skill')}\n"
        f"tier: {summary['tier']}\n"
        f"mode: {summary['mode']}\n"
        f"exit_code: {summary['exit_code']}\n"
        f"duration_seconds: {summary['duration_seconds']}\n"
        f"started_at: {summary['started_at']}\n"
        f"finished_at: {summary['finished_at']}\n"
        "---\n\n"
        f"# Run {run_id}\n\n"
        "## 5-Axis\n\n"
        f"- non_determinism: {summary['non_determinism']}\n"
        f"- trajectory_complete: {summary['trajectory_complete']}\n"
        f"- oracle_score: {summary['oracle_score']} (threshold {summary['oracle_threshold']})\n"
        f"- cost: {cost['tokens']} tokens · {cost['seconds']}s · {cost['power_wh']} Wh ({cost['mode']})\n"
        f"- hitl: {summary['hitl']['acked']}/{summary['hitl']['requested']}\n",
        encoding="utf-8",
    )
    return out


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="skb-harness")
    p.add_argument("--workflow", default=None)
    p.add_argument("--skill", default=None)
    p.add_argument("--tier", required=True, choices=["L0", "L1", "L2", "L3"])
    p.add_argument("--mode", required=True, choices=["dry-run", "apply", "validate-only"])
    p.add_argument("--target", default=".")
    p.add_argument("--run-id", default=None)
    p.add_argument("--parent-run-id", default=None)
    p.add_argument("--inputs", default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not (args.workflow or args.skill):
        sys.stderr.write("either --workflow or --skill is required\n")
        return 2
    if args.workflow and args.skill:
        sys.stderr.write("--workflow and --skill are mutually exclusive\n")
        return 2

    target = Path(args.target).resolve()
    target.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or _new_run_id(target)
    cost_mode = detect_mode()

    workflow_meta: dict[str, Any] = {}
    workflow_id: str | None = None
    if args.workflow:
        wf_path = Path(args.workflow)
        if not wf_path.is_absolute():
            wf_path = target / wf_path
        workflow_meta = parse_workflow(wf_path)
        workflow_id = workflow_meta.get("id")

    write_manifest(
        target,
        run_id,
        {
            "workflow_id": workflow_id,
            "skill": args.skill,
            "tier": args.tier,
            "mode": args.mode,
            "cost_mode": cost_mode,
            "hitl_ack": False,
            "parent_run_id": args.parent_run_id,
            "started_at": _now_iso(),
            "inputs": {"argv": argv},
        },
    )

    common = _common_fields(args, workflow_id)
    started_at = _now_iso()
    started_mono = time.monotonic()
    emit(target, run_id, {
        "event_type": "run_started",
        "target": str(target),
        "cost_mode": cost_mode,
        "inputs_hash": None,
    }, common)

    # Hub write advisory lock (only for runs that actually touch the hub)
    lock_path = target / HUB_LOCK
    holds_lock = False
    if args.mode == "apply" and (args.skill == "skb-repository-setup" or (workflow_meta.get("category") == "ontology")):
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, f"{run_id}\n".encode("utf-8"))
            os.close(fd)
            holds_lock = True
        except FileExistsError:
            other = lock_path.read_text(encoding="utf-8").strip()
            emit(target, run_id, {
                "event_type": "hitl_request",
                "reason": "hub_write_lock_held",
                "target": "canonical_root_hub.yaml",
                "lock_holder_run_id": other,
                "requires_manual_confirmation": True,
            }, common)
            emit(target, run_id, {
                "event_type": "run_finished",
                "exit_code": 2,
                "duration_seconds": round(time.monotonic() - started_mono, 3),
            }, common)
            return 2

    rc = 0
    outputs: dict[str, Any] = {}
    try:
        if args.skill:
            skill_home = _locate_skill(args.skill)
            if skill_home is None:
                emit(target, run_id, {
                    "event_type": "tier_l0_fail",
                    "reason": "skill_not_installed",
                    "fail_target": args.skill,
                }, common)
                rc = 1
            else:
                rc, step_out = _exec_skill(skill_home, args.skill, target, args.mode)
                outputs[args.skill] = step_out
        else:
            rc, outputs = _exec_workflow(args, workflow_meta, target, run_id)
    finally:
        if holds_lock and lock_path.exists():
            try:
                lock_path.unlink()
            except OSError:
                pass

    # Oracle
    gov = workflow_meta.get("governance", {}) if args.workflow else {}
    oracle_name = gov.get("oracle")
    oracle_threshold = float(gov.get("oracle_threshold", 0.85))
    oracle_result = run_oracle(target, oracle_name, run_context={"run_id": run_id, "target": str(target)})
    emit(target, run_id, {
        "event_type": "oracle_evaluation",
        "oracle": oracle_result["oracle"],
        "score": oracle_result["score"],
        "threshold": oracle_threshold,
        "passed": oracle_result["score"] >= oracle_threshold,
        "details": oracle_result["details"],
    }, common)

    # 5-axis aggregation
    wall = time.monotonic() - started_mono
    cost = _aggregate_cost(target, run_id, wall, cost_mode)
    traj_ok, traj_gaps = _trajectory_complete(target, run_id)
    hitl = _hitl_counts(target, run_id)
    measurement = {
        "event_type": "governance_measurement",
        "non_determinism": 0.0,  # N=1 default; not measured
        "trajectory_complete": traj_ok,
        "trajectory_gaps": traj_gaps,
        "oracle_score": oracle_result["score"],
        "oracle_threshold": oracle_threshold,
        "cost": cost,
        "hitl": hitl,
    }
    emit(target, run_id, measurement, common)

    finished_at = _now_iso()
    finalize_outputs(target, run_id, outputs)

    summary = {
        "workflow_id": workflow_id,
        "skill": args.skill,
        "tier": args.tier,
        "mode": args.mode,
        "exit_code": rc,
        "duration_seconds": round(wall, 3),
        "started_at": started_at,
        "finished_at": finished_at,
        "non_determinism": measurement["non_determinism"],
        "trajectory_complete": traj_ok,
        "oracle_score": oracle_result["score"],
        "oracle_threshold": oracle_threshold,
        "cost": cost,
        "hitl": hitl,
    }
    _write_work_log(target, run_id, summary)
    append_decision(target, run_id, {"step": "run", "branch": "completed", "exit_code": rc})

    emit(target, run_id, {
        "event_type": "run_finished",
        "exit_code": rc,
        "duration_seconds": round(wall, 3),
    }, common)
    return rc


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
