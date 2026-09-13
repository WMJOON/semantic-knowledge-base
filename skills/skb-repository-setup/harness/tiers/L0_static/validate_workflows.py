#!/usr/bin/env python3
"""SPEC §8.1 + integration-SPEC §4.2: workflow yaml schema check.

Two formats are validated (MSO is the structural baseline — see UD-0004):

  · **MSO module + x_msm** (current) — structure under `module:`/named phases is
    delegated to MSO `mso-workflow-design` (`wf_node` schema + `wf_to_ttl`
    SHACL/DAG); the MSM execution contract under `x_msm:` (kind/mode/tool/
    pipeline/governance) is checked here. MSO absent (standalone MSM clone) →
    structural delegation degrades to a notice; the x_msm checks still run.
  · **legacy flat** — every field at top level. Kept for un-converted workflows.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

INDEX_REQUIRED_KEYS = ("workflows:", "id:", "path:", "category:", "kind:")
WORKFLOW_REQUIRED_KEYS = (
    "version:",
    "id:",
    "category:",
    "kind:",
    "mode:",
    "inputs:",
    "outputs:",
    "runtime:",
    "governance:",
)
GOVERNANCE_REQUIRED = ("hitl_required:", "max_retry:")
MODE_VALUES = {"dry-run", "apply", "validate-only"}
KIND_VALUES = {"single", "pipeline"}

# MSO mso-workflow-design scripts (structural baseline). validate_workflows.py
# sits at .../skills/skb-repository-setup/harness/tiers/L0_static/ → parents[7]
# is the monorepo root that also holds 00_multi-swarm-orchestrator/.
_MSO_SCRIPTS = (
    Path(__file__).resolve().parents[7]
    / "00_multi-swarm-orchestrator/repository/skills/mso-workflow-design/scripts"
)


def _block(text: str, name: str) -> str:
    """Dedented body of a top-level `name:` block (mirrors workflow_parser._block)."""
    m = re.search(rf"^{re.escape(name)}:[^\n]*\n", text, re.MULTILINE)
    if not m:
        return ""
    body: list[str] = []
    for line in text[m.end():].splitlines():
        if line.strip() == "":
            body.append(line)
            continue
        if not line[:1].isspace():
            break
        body.append(line)
    indents = [len(l) - len(l.lstrip()) for l in body if l.strip()]
    base = min(indents) if indents else 0
    return "\n".join(l[base:] if len(l) >= base else l for l in body)


def _scalar(block: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:\s*([^\n#]+?)\s*(?:#.*)?$", block, re.MULTILINE)
    return m.group(1).strip().strip("\"'") if m else None


def _is_layered(text: str) -> bool:
    """MSO module + x_msm format (vs legacy flat)."""
    return bool(re.search(r"^x_msm:", text, re.MULTILINE)) or bool(
        re.search(r"^module:", text, re.MULTILINE)
    )


def _delegate_structure(path: Path) -> list[str]:
    """Run MSO wf_node(schema) + wf_to_ttl(SHACL/DAG). MSO absent → degrade notice."""
    wf_node = _MSO_SCRIPTS / "wf_node.py"
    wf_to_ttl = _MSO_SCRIPTS / "wf_to_ttl.py"
    if not wf_node.exists():
        print(
            f"  [degrade] MSO mso-workflow-design 부재 — 구조 검증 위임 생략: {path.name}",
            file=sys.stderr,
        )
        return []
    errs: list[str] = []
    for script, kind in ((wf_node, "wf_node"), (wf_to_ttl, "wf_to_ttl")):
        if not script.exists():
            continue
        try:
            r = subprocess.run(
                [sys.executable, str(script), "validate", str(path)],
                capture_output=True, text=True, timeout=3,
            )
        except subprocess.TimeoutExpired:
            print(
                f"  [degrade] MSO {kind} 구조 검증 timeout — x_msm 계약만 검증: {path.name}",
                file=sys.stderr,
            )
            continue
        if r.returncode != 0:
            errs.append(f"MSO {kind} 구조 검증 실패:\n{r.stdout}{r.stderr}".rstrip())
    return errs


def check_workflow_layered(path: Path, text: str) -> list[str]:
    """MSO+x_msm format: delegate structure to MSO, check x_msm execution contract."""
    errs = _delegate_structure(path)

    xmsm = _block(text, "x_msm")
    if not xmsm:
        errs.append("x_msm: 실행 계약 블록 없음 (MSO 구조만으로는 skb-harness 실행 불가)")
        return errs

    for k in ("kind", "mode", "governance"):
        if not re.search(rf"^{k}:", xmsm, re.MULTILINE):
            errs.append(f"x_msm missing key: {k}")
    gov = _block(xmsm, "governance") or xmsm
    for gk in GOVERNANCE_REQUIRED:
        if gk not in gov:
            errs.append(f"x_msm.governance missing {gk}")

    mode = _scalar(xmsm, "mode")
    if mode and mode not in MODE_VALUES:
        errs.append(f"x_msm.mode invalid: {mode}")
    kind = _scalar(xmsm, "kind")
    if kind:
        if kind not in KIND_VALUES:
            errs.append(f"x_msm.kind invalid: {kind}")
        elif kind == "single" and not _scalar(xmsm, "tool"):
            errs.append("x_msm.kind=single requires x_msm.tool:")
        elif kind == "pipeline" and not re.search(r"^pipeline:", xmsm, re.MULTILINE):
            errs.append("x_msm.kind=pipeline requires x_msm.pipeline: block")
    return errs


def check_workflow_flat(path: Path, text: str) -> list[str]:
    """legacy flat format: every field at top level."""
    errs: list[str] = []
    for k in WORKFLOW_REQUIRED_KEYS:
        if k not in text:
            errs.append(f"missing key: {k}")
    for k in GOVERNANCE_REQUIRED:
        if k not in text:
            errs.append(f"missing governance.{k}")
    m = re.search(r"\nmode:\s*([^\s\n]+)", text)
    if m and m.group(1) not in MODE_VALUES:
        errs.append(f"mode invalid: {m.group(1)}")
    m = re.search(r"\nkind:\s*([^\s\n]+)", text)
    if m:
        if m.group(1) not in KIND_VALUES:
            errs.append(f"kind invalid: {m.group(1)}")
        elif m.group(1) == "single" and not re.search(r"\ntool:\s*\S", text):
            errs.append("kind=single requires top-level tool:")
        elif m.group(1) == "pipeline" and "\npipeline:" not in text:
            errs.append("kind=pipeline requires pipeline: block")
    return errs


def check_workflow(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if _is_layered(text):
        return check_workflow_layered(path, text)
    return check_workflow_flat(path, text)


def _workflow_root(target: Path) -> Path:
    canonical = target / "agent-context" / "workflow"
    return canonical if canonical.exists() else target / "workflow"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--workflow", default=None, help="check a single yaml file")
    args = ap.parse_args()
    target = Path(args.target).resolve()

    if args.workflow:
        single = Path(args.workflow)
        if not single.is_absolute():
            single = target / single
        errs = check_workflow(single)
        if errs:
            print(f"FAIL: {single}", file=sys.stderr)
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            return 1
        print(f"OK: {single}")
        return 0

    workflow_root = _workflow_root(target)
    index = workflow_root / "index.yaml"
    if not index.exists():
        print("FAIL: agent-context/workflow/index.yaml not found", file=sys.stderr)
        return 1
    idx_text = index.read_text(encoding="utf-8")
    for k in INDEX_REQUIRED_KEYS:
        if k not in idx_text:
            print(f"FAIL: {index.relative_to(target)} missing {k}", file=sys.stderr)
            return 1

    yamls = [p for p in workflow_root.rglob("*.yaml") if p.name != "index.yaml"]
    if not yamls:
        print(f"FAIL: no workflow yaml under {workflow_root.relative_to(target)}/", file=sys.stderr)
        return 1
    total_errs = 0
    for p in yamls:
        errs = check_workflow(p)
        if errs:
            total_errs += len(errs)
            print(f"FAIL: {p.relative_to(target)}", file=sys.stderr)
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
    if total_errs:
        return 1
    print(f"OK: {len(yamls)} workflow yaml(s) valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
