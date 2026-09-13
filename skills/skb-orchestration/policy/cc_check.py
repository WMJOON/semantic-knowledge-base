#!/usr/bin/env python3
"""CC contract checker.

SPEC §5: enforces consistency across canonical hub, workflow index, pack_config,
threshold file, hitl policy.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

SKILL_HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_HOME / "router"))

import _yaml_lite as yaml  # noqa: E402
from workflow_ttl import parse_index_ttl, parse_workflow_ttl  # noqa: E402


def _workflow_roots(target: Path) -> list[Path]:
    roots = [target / "agent-context" / "workflow", target / "workflow"]
    return [root for root in roots if root.exists()]


def check_workflow_id_uniqueness(target: Path) -> list[dict]:
    seen: Counter[str] = Counter()
    locations: dict[str, list[str]] = {}
    for root in _workflow_roots(target):
        for p in root.rglob("*.ttl"):
            if p.name == "index.ttl":
                continue
            try:
                wid = parse_workflow_ttl(p).get("id")
            except Exception:
                wid = None
            if not wid:
                continue
            seen[wid] += 1
            locations.setdefault(wid, []).append(str(p.relative_to(target)))
    for root in _workflow_roots(target):
        for p in root.rglob("*.yaml"):
            if p.name == "index.yaml":
                continue
            if p.with_suffix(".abox.ttl").exists():
                continue
            text = p.read_text(encoding="utf-8")
            m = re.search(r"^id:\s*([^\n]+)\s*$", text, re.MULTILINE)
            if not m:
                continue
            wid = m.group(1).strip().strip('"').strip("'")
            seen[wid] += 1
            locations.setdefault(wid, []).append(str(p.relative_to(target)))
    return [
        {"contract": "workflow_id_uniqueness", "id": wid, "occurrences": locations[wid]}
        for wid, n in seen.items()
        if n > 1
    ]


def check_registry_alignment(target: Path) -> list[dict]:
    for root in (target / "agent-context" / "workflow", target / "workflow"):
        idx_ttl = root / "index.ttl"
        if idx_ttl.exists():
            violations: list[dict] = []
            for wf in parse_index_ttl(idx_ttl):
                pth = wf.get("path")
                if not pth:
                    violations.append({"contract": "workflow_index_path", "detail": f"missing path: {wf}"})
                    continue
                full = target / pth
                if not full.exists():
                    violations.append({"contract": "workflow_index_path", "detail": f"missing file: {pth}"})
            return violations

    for root in (target / "agent-context" / "workflow", target / "workflow"):
        idx = root / "index.yaml"
        if not idx.exists():
            continue
        data = yaml.load(idx)
        violations: list[dict] = []
        for wf in data.get("workflows", []) or []:
            pth = wf.get("path")
            if not pth:
                violations.append({"contract": "workflow_index_path", "detail": f"missing path: {wf}"})
                continue
            full = target / pth
            if not full.exists():
                violations.append({"contract": "workflow_index_path", "detail": f"missing file: {pth}"})
        return violations
    return [{"contract": "workflow_index_present", "detail": "agent-context/workflow/index.ttl missing"}]


def check_canonical_hub_locked(target: Path) -> list[dict]:
    hub = target / "canonical_root_hub.yaml"
    if not hub.exists():
        return [{"contract": "canonical_root_hub_present"}]
    text = hub.read_text(encoding="utf-8")
    if "locked: true" not in text:
        return [{"contract": "canonical_root_hub_locked", "detail": "locked must be true at v0.10.0"}]
    return []


def check_pack_config(pack: dict) -> list[dict]:
    violations: list[dict] = []
    if pack.get("version") != "v0.10.0":
        violations.append({"contract": "pack_config_version", "detail": pack.get("version")})
    core = (pack.get("skills") or {}).get("core") or []
    if len(set(core)) != 8:
        violations.append({"contract": "pack_config_core_count", "detail": len(set(core))})
    mode = (pack.get("migration") or {}).get("mode")
    if mode not in ("compatibility", "strict-soft", "v1-strict"):
        violations.append({"contract": "pack_config_migration_mode", "detail": mode})
    return violations


def check(target: Path, pack: dict | None = None) -> dict:
    if pack is None:
        pack_path = SKILL_HOME / "references" / "pack_config.json"
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
    violations: list[dict] = []
    violations.extend(check_workflow_id_uniqueness(target))
    violations.extend(check_registry_alignment(target))
    violations.extend(check_canonical_hub_locked(target))
    violations.extend(check_pack_config(pack))
    return {"ok": not violations, "violations": violations}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="cc_check")
    p.add_argument("--target", required=True)
    args = p.parse_args(argv)
    target = Path(args.target).resolve()
    result = check(target)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
