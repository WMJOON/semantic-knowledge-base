"""Resolve workflow_id → on-disk path via MSO canonical workflow index.

SPEC §4.2 step 4.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _yaml_lite as yaml  # noqa: E402
from workflow_ttl import parse_index_ttl  # noqa: E402


def resolve(target: Path, workflow_id: str) -> dict | None:
    roots = (target / "agent-context" / "workflow", target / "workflow")
    for root in roots:
        ttl_path = root / "index.ttl"
        if ttl_path.exists():
            for wf in parse_index_ttl(ttl_path):
                if wf.get("id") == workflow_id:
                    return wf

    for root in roots:
        idx_path = root / "index.yaml"
        if not idx_path.exists():
            continue
        data = yaml.load(idx_path)
        for wf in data.get("workflows", []) or []:
            if wf.get("id") == workflow_id:
                return wf
    return None


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="resolve_workflow")
    p.add_argument("--target", required=True)
    p.add_argument("--workflow-id", required=True)
    args = p.parse_args(argv)
    target = Path(args.target).resolve()
    wf = resolve(target, args.workflow_id)
    if wf is None:
        print(json.dumps({"error": "workflow_not_found", "workflow_id": args.workflow_id}))
        return 1
    print(json.dumps(wf, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
