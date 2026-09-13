#!/usr/bin/env python3
"""Apply a plan produced by plan_init.py."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from manifest import build_manifest  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="apply_init")
    # Mirror plan_init so we can run end-to-end in one call.
    p.add_argument("--target", default=".")
    p.add_argument("--name", default=None)
    p.add_argument("--domain", default=None)
    p.add_argument("--root-hub", default=None)
    p.add_argument("--targets", default="claude,codex")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--with-skill-links", action="store_true")
    p.add_argument("--with-venv", action="store_true")
    p.add_argument("--templates", default=None)
    p.add_argument("--yes", action="store_true")
    p.add_argument("--plan", default=None, help="path to plan JSON; if omitted, runs plan_init")
    p.add_argument("--run-id", default=None)
    return p.parse_args(argv)


def load_or_build_plan(args: argparse.Namespace) -> dict:
    if args.plan:
        return json.loads(Path(args.plan).read_text(encoding="utf-8"))
    import plan_init  # noqa: WPS433

    plan_argv = [
        "--target", args.target,
        "--targets", args.targets,
    ]
    if args.name:
        plan_argv += ["--name", args.name]
    if args.domain:
        plan_argv += ["--domain", args.domain]
    if args.root_hub:
        plan_argv += ["--root-hub", args.root_hub]
    if args.strict:
        plan_argv.append("--strict")
    if args.with_skill_links:
        plan_argv.append("--with-skill-links")
    if args.with_venv:
        plan_argv.append("--with-venv")
    if args.templates:
        plan_argv += ["--templates", args.templates]
    if args.run_id:
        plan_argv += ["--run-id", args.run_id]
    ns = plan_init.parse_args(plan_argv)
    return plan_init.build_plan(ns)


def substitute_template(text: str, args: argparse.Namespace) -> str:
    domain = args.domain or ""
    label = domain.replace("_", " ").title() if domain else ""
    name = args.name or Path(args.target).resolve().name
    return (
        text.replace("{{KB_NAME}}", name)
        .replace("{{CLUSTER}}", domain)
        .replace("{{LABEL}}", label or name)
    )


def write_trajectory(target: Path, run_id: str, event: dict) -> None:
    traj_dir = target / "harness" / "trajectory"
    traj_dir.mkdir(parents=True, exist_ok=True)
    out = {"run_id": run_id, **event}
    line = json.dumps(out, ensure_ascii=False)
    (traj_dir / f"run-{run_id}.jsonl").open("a", encoding="utf-8").write(line + "\n")


def maybe_register_domain(target: Path, domain: str | None, hitl_ack: bool) -> bool:
    """Insert domain entry into canonical_root_hub.yaml.

    Returns True on success. Returns False (no-op) when hub is locked and the
    domain is not yet registered and we don't have HITL ack.
    """
    if not domain:
        return True
    hub = target / "canonical_root_hub.yaml"
    text = hub.read_text(encoding="utf-8")
    if f"name: {domain}" in text:
        return True
    if "locked: true" in text and not hitl_ack:
        return False
    today = _dt.date.today().isoformat()
    label = domain.replace("_", " ").title()
    entry = (
        f"  - name: {domain}\n"
        f"    label: \"{label}\"\n"
        f"    semantic_graph: \"ontology/system/semantic/{domain}/{domain}.ttl\"\n"
        f"    root_hub: \"projection/wikigraph/class/{domain}/{domain}__class.md\"\n"
        f"    description: \"{label} ontology cluster\"\n"
        f"    status: draft\n"
        f"    owner: null\n"
        f"    archived_at: \"{today}\"\n"
        f"    updated_at: \"{today}\"\n"
    )
    # Replace `domains: []` with a list, or append to existing list.
    if "domains: []" in text:
        new_text = text.replace("domains: []", "domains:\n" + entry.rstrip("\n"))
    else:
        # Append immediately after the `domains:` block; we add at end of file
        # as a conservative fallback when the parse is ambiguous.
        # SPEC contract: hub registry stays valid; tests cover the empty case.
        new_text = text.rstrip() + "\n" + entry
    hub.write_text(new_text, encoding="utf-8")
    return True


def apply(plan: dict, args: argparse.Namespace) -> int:
    target = Path(plan["target"]).resolve()
    target.mkdir(parents=True, exist_ok=True)
    run_id = plan["run_id"]
    templates_dir = Path(plan["options"]["templates"])

    write_trajectory(target, run_id, {"event_type": "repository_setup_plan", "creates": [c["path"] for c in plan["creates"]], "conflicts": [c["path"] for c in plan["conflicts"]]})

    hitl_ack = args.yes
    if plan["conflicts"] and not hitl_ack:
        for hitl in plan["hitl_requests"]:
            write_trajectory(target, run_id, hitl)
        sys.stderr.write(
            "apply aborted: {n} conflict(s); pass --yes after HITL review\n".format(
                n=len(plan["conflicts"])
            )
        )
        return 1

    # Create dirs first
    for item in plan["creates"]:
        if item["kind"] == "dir":
            (target / item["path"]).mkdir(parents=True, exist_ok=True)

    # Then files
    for item in plan["creates"]:
        out_path = target / item["path"]
        if item["kind"] == "file_empty":
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.touch(exist_ok=True)
            continue
        if item["kind"] in ("file_template", "file_executable"):
            template_rel = item.get("template")
            if not template_rel:
                continue
            src = templates_dir / template_rel
            content = src.read_text(encoding="utf-8")
            content = substitute_template(content, args)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            if item["kind"] == "file_executable":
                out_path.chmod(0o755)
            continue

    # Register domain (after files exist) and emit HITL request if blocked.
    if not maybe_register_domain(target, args.domain, hitl_ack):
        write_trajectory(
            target,
            run_id,
            {
                "event_type": "hitl_request",
                "requires_manual_confirmation": True,
                "reason": "canonical_root_hub_locked_change",
                "target": "canonical_root_hub.yaml",
                "proposed_action": f"register_domain:{args.domain}",
            },
        )
        # Domain registration blocked but other files applied; return non-zero
        # so caller knows manual step is pending.
        write_trajectory(target, run_id, {"event_type": "apply_partial", "blocked": "domain_registration"})
        return 2

    # Optional skill links (delegated to repository/install.sh)
    if args.with_skill_links:
        installer = Path(__file__).resolve().parents[2] / "install.sh"
        if installer.exists():
            write_trajectory(target, run_id, {"event_type": "skill_links_invoke", "installer": str(installer)})
            # Defer real execution: legacy installer touches user $HOME so we
            # only record intent unless --yes is set.
            if hitl_ack:
                rc = subprocess.run(["bash", str(installer)], check=False).returncode
                write_trajectory(target, run_id, {"event_type": "skill_links_done", "exit_code": rc})

    # Optional venv
    if args.with_venv:
        venv_path = target / ".venv"
        if not venv_path.exists():
            subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=False)
            write_trajectory(target, run_id, {"event_type": "venv_created", "path": str(venv_path)})

    # Generate / update index.yaml (mso-scaffold-design v2 schema)
    # dry-run: generate 없이 결과만 출력. apply: 실제 파일 생성.
    try:
        from gen_index import gen_or_update_index  # noqa: WPS433
        idx_result = gen_or_update_index(
            target,
            name=getattr(args, "name", None),
            domain=getattr(args, "domain", None),
            dry_run=not hitl_ack,
        )
        write_trajectory(
            target, run_id,
            {"event_type": "index_yaml_gen", "result": idx_result, "path": "index.yaml"},
        )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[apply_init] index.yaml 생성 건너뜀: {exc}\n")

    # Readiness scoring
    score_path = Path(__file__).resolve().parent / "score_readiness.py"
    rc = subprocess.run(
        [sys.executable, str(score_path), "--target", str(target), "--run-id", run_id],
        check=False,
    ).returncode
    return rc


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not args.templates:
        args.templates = str(SCRIPT_DIR.parents[2] / "templates")
    plan = load_or_build_plan(args)
    return apply(plan, args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
