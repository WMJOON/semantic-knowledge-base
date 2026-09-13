"""Threshold resolver.

SPEC §6.1: resolution order is workflow_id override → category override → defaults.
Each axis returns a fully-merged dict starting from defaults and overlaying overrides.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

SKILL_HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_HOME / "router"))

import _yaml_lite as yaml  # noqa: E402

REF = SKILL_HOME / "references" / "5-axis-thresholds.yaml"


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = deepcopy(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def resolve(workflow_id: str | None = None,
            category: str | None = None,
            path: Path = REF) -> dict[str, Any]:
    data = yaml.load(path)
    resolved = deepcopy(data.get("defaults", {}) or {})
    overrides = data.get("overrides", {}) or {}
    # Category override applied first; workflow_id override wins later (highest priority).
    by_cat = (overrides.get("by_category") or {}).get(category) if category else None
    if by_cat:
        resolved = _deep_merge(resolved, by_cat)
    by_wf = (overrides.get("by_workflow_id") or {}).get(workflow_id) if workflow_id else None
    if by_wf:
        resolved = _deep_merge(resolved, by_wf)
    return resolved
