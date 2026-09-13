#!/usr/bin/env python3
"""skb-orchestration dispatch entry.

End-to-end: intent → route → CC check → harness run → gate evaluator.
SPEC §4, §5, §6, §9, §12.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_HOME = SCRIPT_DIR.parents[0]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SKILL_HOME / "policy"))

import _yaml_lite as yaml  # noqa: E402
import match_trigger  # noqa: E402
import mirror_writer as mw  # noqa: E402
import resolve_workflow  # noqa: E402

GATE = None  # late import to keep error messages tidy


def _new_run_id(target: Path) -> str:
    base = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    traj = target / "harness" / "trajectory"
    slot = target / ".msm-context" / "active"
    cand = base
    for _ in range(8):
        if not (traj / f"run-{cand}.jsonl").exists() and not (slot / cand).exists():
            return cand
        cand = f"{base}-{secrets.token_hex(2)}"
    return cand


def _load_pack_config() -> dict:
    p = SKILL_HOME / "references" / "pack_config.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _locate_harness_runtime() -> Path | None:
    env = os.environ.get("MSM_HARNESS_HOME")
    candidates = []
    if env:
        candidates.append(Path(env) / "runtime" / "run.sh")
    candidates.append(SKILL_HOME.parent / "skb-harness" / "runtime" / "run.sh")
    candidates.append(Path.home() / ".skill-modules" / "msm-skills" / "skb-harness" / "runtime" / "run.sh")
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return c
    return None


def _exec_harness(target: Path, run_id: str, route: dict, mode: str | None) -> int:
    runtime = _locate_harness_runtime()
    if runtime is None:
        return 127
    args = ["--tier", route.get("tier", "L0"), "--mode", mode or route.get("default_mode", "dry-run"),
            "--target", str(target), "--run-id", run_id]
    if route.get("mode") == "skill":
        args = ["--skill", route["skill"]] + args
    elif route.get("workflow_path"):
        args = ["--workflow", route["workflow_path"]] + args
    else:
        # Resolve workflow_id via target/agent-context/workflow/index.ttl,
        # falling back to legacy target/workflow/index.{ttl,yaml}.
        wf = resolve_workflow.resolve(target, route["workflow_id"])
        if wf is None:
            return 1
        args = ["--workflow", wf["path"]] + args
    return subprocess.run([str(runtime)] + args, check=False).returncode


def _invoke_gate(target: Path, run_id: str, workflow_id: str | None, category: str | None) -> int:
    global GATE
    if GATE is None:
        sys.path.insert(0, str(SKILL_HOME / "policy"))
        import gate_evaluator as _g  # noqa: WPS433
        GATE = _g
    return GATE.evaluate_and_emit(target, run_id, workflow_id=workflow_id, category=category)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="skb-orchestration")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--intent", help="natural-language intent to route")
    g.add_argument("--workflow", help="explicit workflow ttl/yaml path (relative to target or absolute)")
    g.add_argument("--skill", help="explicit skill name (bypasses router)")
    p.add_argument("--target", default=".")
    p.add_argument("--mode", default=None, help="override workflow.mode (dry-run/apply/validate-only)")
    p.add_argument("--tier", default=None, help="override tier (L0..L3)")
    p.add_argument("--strict", action="store_true", help="treat run as v1-strict regardless of pack_config")
    p.add_argument("--no-gate", action="store_true", help="skip the post-run gate evaluation")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    target = Path(args.target).resolve()
    target.mkdir(parents=True, exist_ok=True)
    run_id = _new_run_id(target)

    pack = _load_pack_config()
    migration_mode = "v1-strict" if args.strict else pack.get("migration", {}).get("mode", "compatibility")

    # CC check pre-flight (fail fast)
    from cc_check import check as cc_check  # noqa: WPS433
    cc = cc_check(target, pack=pack)
    if not cc["ok"]:
        for violation in cc["violations"]:
            mw.emit(target, run_id, {"event_type": "cc_violation", **violation})
        sys.stderr.write(f"CC violation: {cc['violations']}\n")
        return 1

    # Resolve route
    route: dict
    workflow_id: str | None = None
    category: str | None = None
    legacy_alias_hit: str | None = None

    if args.skill:
        route = {"mode": "skill", "skill": args.skill, "tier": args.tier or "L0", "default_mode": "validate-only"}
    elif args.workflow:
        wf_path = Path(args.workflow)
        if not wf_path.is_absolute():
            wf_path = target / wf_path
        if not wf_path.exists():
            mw.emit(target, run_id, {"event_type": "cc_violation", "contract": "workflow_path",
                                     "detail": f"missing: {wf_path}"})
            return 1
        from workflow_meta import read_meta  # noqa: WPS433
        meta = read_meta(wf_path)
        workflow_id = meta.get("id")
        category = meta.get("category")
        # Explicit --workflow path bypasses the registry lookup so ad-hoc workflow
        # workflows that aren't in the workflow registry can still be dispatched.
        route = {"mode": "workflow", "workflow_id": workflow_id, "tier": args.tier or "L0",
                 "default_mode": meta.get("mode", "dry-run"),
                 "workflow_path": str(wf_path)}
    else:
        m = match_trigger.match(args.intent)
        if m is None:
            mw.emit(target, run_id, {"event_type": "routing_decision", "trigger_id": None,
                                     "matched_keywords": [], "workflow_id": None,
                                     "mode": "none", "reason": "no_match"})
            sys.stderr.write(f"no trigger matched intent: {args.intent}\n")
            return 1
        route = m["route"]
        # Detect legacy alias hits
        legacy_keywords = set(m.get("legacy_aliases") or [])
        for hit in m["matched_keywords"]:
            if hit in legacy_keywords:
                legacy_alias_hit = hit
                break
        if legacy_alias_hit:
            if migration_mode == "v1-strict":
                mw.emit(target, run_id, {"event_type": "deprecated_route", "from": legacy_alias_hit,
                                         "to": route.get("workflow_id") or route.get("skill"),
                                         "reason": "v0.2.0→v0.10.0 migration",
                                         "rejected": True, "mode": migration_mode})
                sys.stderr.write(f"v1-strict: legacy route {legacy_alias_hit} rejected\n")
                return 102
            mw.emit(target, run_id, {"event_type": "deprecated_route", "from": legacy_alias_hit,
                                     "to": route.get("workflow_id") or route.get("skill"),
                                     "reason": "v0.2.0→v0.10.0 migration", "mode": migration_mode})
        if route.get("mode") == "workflow":
            workflow_id = route.get("workflow_id")
            # Lookup category via workflow index
            wf = resolve_workflow.resolve(target, workflow_id) if workflow_id else None
            if wf:
                category = wf.get("category")

        mw.emit(target, run_id, {"event_type": "routing_decision", "trigger_id": m["trigger_id"],
                                 "matched_keywords": m["matched_keywords"],
                                 "workflow_id": workflow_id, "mode": route.get("mode"),
                                 "legacy_aliases_hit": [legacy_alias_hit] if legacy_alias_hit else []})

    # If hooks_disabled env var set, mirror it for audit
    if os.environ.get("MSM_HOOKS_DISABLED") == "1":
        mw.emit(target, run_id, {"event_type": "hooks_disabled", "value": True})

    # Invoke harness
    rc = _exec_harness(target, run_id, route, args.mode)

    # Gate evaluation (unless --no-gate or harness lookup failed)
    if not args.no_gate:
        gate_rc = _invoke_gate(target, run_id, workflow_id=workflow_id, category=category)
        # Gate failure can override harness rc per SPEC §9.4
        if gate_rc != 0 and rc == 0:
            rc = gate_rc

    return rc


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
