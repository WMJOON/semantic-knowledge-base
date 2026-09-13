"""Orchestration mirror trajectory writer.

SPEC §10.3: orchestration events go to a separate file alongside harness
trajectory so the harness file stays measurement-only.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any


def mirror_file(target: Path, run_id: str) -> Path:
    out = target / "harness" / "trajectory" / f"run-{run_id}.orchestration.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def _now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def emit(target: Path, run_id: str, event: dict[str, Any]) -> None:
    record = {"run_id": run_id, "ts": _now_iso(), **event}
    path = mirror_file(target, run_id)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (line + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def read(target: Path, run_id: str) -> list[dict[str, Any]]:
    path = mirror_file(target, run_id)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out
