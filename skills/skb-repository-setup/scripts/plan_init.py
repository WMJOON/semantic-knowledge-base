#!/usr/bin/env python3
"""DISCOVERY -> PLAN -> VALIDATE for `skb init`.

Reads target tree, compares to manifest, classifies each entry, and
emits a JSON plan on stdout. Does NOT touch the filesystem.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import secrets
import sys
from pathlib import Path


def _uniq_run_id(target: Path) -> str:
    base = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    traj = target / "harness" / "trajectory"
    slot = target / ".msm-context" / "active"
    candidate = base
    for _ in range(8):
        if not (traj / f"run-{candidate}.jsonl").exists() and not (slot / candidate).exists():
            return candidate
        candidate = f"{base}-{secrets.token_hex(2)}"
    return candidate

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from manifest import Entry, build_manifest, has_marker  # noqa: E402


REPO_ROOT_DEFAULT = SCRIPT_DIR.parents[2]
DEFAULT_TEMPLATES = REPO_ROOT_DEFAULT / "templates"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="plan_init")
    p.add_argument("--target", default=".")
    p.add_argument("--name", default=None)
    p.add_argument("--domain", default=None)
    p.add_argument("--root-hub", default=None)
    p.add_argument("--targets", default="claude,codex")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--with-skill-links", action="store_true")
    p.add_argument("--with-venv", action="store_true")
    p.add_argument("--templates", default=str(DEFAULT_TEMPLATES))
    p.add_argument("--run-id", default=None)
    return p.parse_args(argv)


def classify(target: Path, entry: Entry) -> dict:
    abs_path = target / entry.path
    if entry.kind == "dir":
        if not abs_path.exists():
            return {"action": "create", "path": entry.path, "kind": "dir"}
        if abs_path.is_dir():
            return {"action": "keep", "path": entry.path, "kind": "dir"}
        return {
            "action": "conflict",
            "path": entry.path,
            "kind": "dir",
            "reason": "non_directory_at_dir_path",
        }
    if entry.kind == "file_empty":
        if not abs_path.exists():
            return {"action": "create", "path": entry.path, "kind": "file_empty"}
        return {"action": "keep", "path": entry.path, "kind": "file_empty"}
    # template / executable
    if not abs_path.exists():
        return {
            "action": "create",
            "path": entry.path,
            "kind": entry.kind,
            "template": entry.template,
        }
    try:
        content = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "action": "conflict",
            "path": entry.path,
            "kind": entry.kind,
            "reason": f"read_error:{exc!s}",
        }
    if has_marker(content, entry.marker):
        return {
            "action": "keep",
            "path": entry.path,
            "kind": entry.kind,
            "template": entry.template,
        }
    return {
        "action": "conflict",
        "path": entry.path,
        "kind": entry.kind,
        "reason": "non_generated_file_exists",
        "template": entry.template,
    }


def build_plan(args: argparse.Namespace) -> dict:
    target = Path(args.target).resolve()
    targets = tuple(t.strip() for t in args.targets.split(",") if t.strip())
    manifest = build_manifest(targets=targets, domain=args.domain)
    creates: list[dict] = []
    keeps: list[dict] = []
    conflicts: list[dict] = []
    for entry in manifest:
        result = classify(target, entry)
        bucket = {"create": creates, "keep": keeps, "conflict": conflicts}[result["action"]]
        bucket.append(result)

    hitl_requests: list[dict] = []
    for c in conflicts:
        hitl_requests.append(
            {
                "event_type": "hitl_request",
                "requires_manual_confirmation": True,
                "reason": c["reason"],
                "target": c["path"],
                "proposed_action": "skip_or_backup_then_replace",
            }
        )

    # Canonical hub locked-change detection: if hub exists already and we plan
    # to add a domain, that's an Always-HITL event (SPEC §9.1).
    hub_path = target / "canonical_root_hub.yaml"
    if args.domain and hub_path.exists():
        hub_text = hub_path.read_text(encoding="utf-8", errors="replace")
        if "locked: true" in hub_text and f"name: {args.domain}" not in hub_text:
            hitl_requests.append(
                {
                    "event_type": "hitl_request",
                    "requires_manual_confirmation": True,
                    "reason": "canonical_root_hub_locked_change",
                    "target": "canonical_root_hub.yaml",
                    "proposed_action": f"register_domain:{args.domain}",
                }
            )

    run_id = args.run_id or _uniq_run_id(target)
    return {
        "run_id": run_id,
        "event_type": "repository_setup_plan",
        "target": str(target),
        "mode": "dry-run",
        "options": {
            "name": args.name,
            "domain": args.domain,
            "root_hub": args.root_hub,
            "targets": list(targets),
            "strict": args.strict,
            "with_skill_links": args.with_skill_links,
            "with_venv": args.with_venv,
            "templates": str(Path(args.templates).resolve()),
        },
        "creates": creates,
        "keeps": keeps,
        "conflicts": conflicts,
        "hitl_requests": hitl_requests,
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    plan = build_plan(args)
    json.dump(plan, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if not plan["conflicts"] else 0  # plan stage never fails on conflicts


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
