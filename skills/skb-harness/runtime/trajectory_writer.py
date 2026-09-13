"""Append-only writer for harness/trajectory/run-<run_id>.jsonl.

SPEC: skb-harness-SPEC §8. truncate/rewrite 금지, atomic append.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def trajectory_file(target: Path, run_id: str) -> Path:
    out = target / "harness" / "trajectory" / f"run-{run_id}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def emit(target: Path, run_id: str, event: dict[str, Any], common: dict[str, Any] | None = None) -> None:
    common = common or {}
    record: dict[str, Any] = {
        "run_id": run_id,
        "ts": _now_iso(),
        **common,
        **event,
    }
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    path = trajectory_file(target, run_id)
    # O_APPEND atomic single-write for short lines (POSIX guarantee on local fs)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (line + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def read_events(target: Path, run_id: str) -> list[dict[str, Any]]:
    path = trajectory_file(target, run_id)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events
