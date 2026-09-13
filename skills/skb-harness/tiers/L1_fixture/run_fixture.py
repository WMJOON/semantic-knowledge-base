#!/usr/bin/env python3
"""L1 fixture runner.

SPEC §6: L1 takes a fixture yaml + deterministic inputs and asserts the
expected plan/output shape. Scratch dir only — no real target mutation.

Initial scope: harness/fixtures/<name>.yaml of the form

    fixture:
      name: ...
      inputs:
        target: ":scratch:/<name>"
        options: { ... }
      expected:
        plan:
          creates_min: <int>
          conflicts: <int>
          hitl_requests: <int>
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _read_field(text: str, field: str) -> str | None:
    m = re.search(rf"^\s*{re.escape(field)}:\s*([^\n]+)\s*$", text, re.MULTILINE)
    if not m:
        return None
    v = m.group(1).strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    return v


def _read_int(text: str, field: str, default: int = 0) -> int:
    v = _read_field(text, field)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="run_fixture")
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--skill", default="skb-repository-setup")
    ap.add_argument("--scratch", default=None)
    args = ap.parse_args(argv)
    fixture_path = Path(args.fixture).resolve()
    text = fixture_path.read_text(encoding="utf-8")

    name = _read_field(text, "name") or fixture_path.stem
    creates_min = _read_int(text, "creates_min", 0)
    expected_conflicts = _read_int(text, "conflicts", 0)
    expected_hitl = _read_int(text, "hitl_requests", 0)

    scratch = Path(args.scratch) if args.scratch else Path(tempfile.mkdtemp(prefix="msm-l1-"))
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)

    here = Path(__file__).resolve()
    msm_cli = here.parents[3] / args.skill / "scripts" / "msm"
    if not msm_cli.exists():
        print(f"FAIL: {args.skill} CLI not found: {msm_cli}", file=sys.stderr)
        return 1

    plan = subprocess.run([str(msm_cli), "init", "--target", str(scratch)], check=False, capture_output=True, text=True)
    if plan.returncode != 0:
        print(f"FAIL: plan exit {plan.returncode}: {plan.stderr.strip()}", file=sys.stderr)
        return 1
    try:
        data = json.loads(plan.stdout)
    except json.JSONDecodeError as e:
        print(f"FAIL: plan json: {e}", file=sys.stderr)
        return 1

    creates = len(data.get("creates", []))
    conflicts = len(data.get("conflicts", []))
    hitls = len(data.get("hitl_requests", []))

    ok = True
    if creates < creates_min:
        print(f"FAIL[{name}]: creates {creates} < expected_min {creates_min}", file=sys.stderr)
        ok = False
    if conflicts != expected_conflicts:
        print(f"FAIL[{name}]: conflicts {conflicts} != expected {expected_conflicts}", file=sys.stderr)
        ok = False
    if hitls != expected_hitl:
        print(f"FAIL[{name}]: hitl_requests {hitls} != expected {expected_hitl}", file=sys.stderr)
        ok = False

    if ok:
        print(f"OK[{name}]: creates={creates} conflicts={conflicts} hitl={hitls}")
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
