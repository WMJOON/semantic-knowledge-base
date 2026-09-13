"""Run context slot manifest writer.

SPEC: skb-harness-SPEC §5. atomic create + append-only mutation.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def slot_dir(target: Path, run_id: str) -> Path:
    return target / ".msm-context" / "active" / run_id


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_manifest(target: Path, run_id: str, fields: dict[str, Any]) -> Path:
    sdir = slot_dir(target, run_id)
    sdir.mkdir(parents=True, exist_ok=True)
    started_at = fields.get("started_at") or _dt.datetime.now(tz=_dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    manifest = {
        "run_id": run_id,
        "workflow_id": fields.get("workflow_id"),
        "skill": fields.get("skill"),
        "tier": fields.get("tier"),
        "mode": fields.get("mode"),
        "target": str(target),
        "started_at": started_at,
        "cost_mode": fields.get("cost_mode", "fallback"),
        "hitl_ack": bool(fields.get("hitl_ack", False)),
        "parent_run_id": fields.get("parent_run_id"),
    }
    # Inline minimal YAML (avoid pyyaml dep)
    lines = []
    for k, v in manifest.items():
        if v is None:
            lines.append(f"{k}: null")
        elif isinstance(v, bool):
            lines.append(f"{k}: {str(v).lower()}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f"{k}: \"{v}\"")
    atomic_write(sdir / "manifest.yaml", "\n".join(lines) + "\n")
    atomic_write(sdir / "inputs.json", json.dumps(fields.get("inputs", {}), ensure_ascii=False, indent=2))
    atomic_write(sdir / "outputs.json", "{}\n")
    (sdir / "decisions.jsonl").touch()
    return sdir


def append_decision(target: Path, run_id: str, decision: dict[str, Any]) -> None:
    sdir = slot_dir(target, run_id)
    sdir.mkdir(parents=True, exist_ok=True)
    fd = os.open(sdir / "decisions.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (json.dumps(decision, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def finalize_outputs(target: Path, run_id: str, outputs: dict[str, Any]) -> None:
    sdir = slot_dir(target, run_id)
    atomic_write(sdir / "outputs.json", json.dumps(outputs, ensure_ascii=False, indent=2))
