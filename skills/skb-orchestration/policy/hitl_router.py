#!/usr/bin/env python3
"""HITL ack router.

Persists user ack into agent-context/work-memory/auditlog/ and emits a
`hitl_ack` event into the orchestration mirror trajectory.

SPEC §7.3, §7.4, AC-ORCH-10.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

SKILL_HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_HOME / "router"))

import mirror_writer as mw  # noqa: E402


def ack(target: Path, run_id: str, topic: str, decided_by: str, outcome: str,
        notes: str | None = None) -> Path:
    decided_at = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dir_ = target / "agent-context" / "work-memory" / "auditlog"
    dir_.mkdir(parents=True, exist_ok=True)
    out = dir_ / f"{run_id}__{topic}.md"
    body = (
        "---\n"
        f"run_id: {run_id}\n"
        f"topic: {topic}\n"
        f"decided_at: {decided_at}\n"
        f"decided_by: {decided_by}\n"
        f"outcome: {outcome}\n"
        "---\n\n"
        "# Decision\n\n"
        f"{notes or ''}\n"
    )
    out.write_text(body, encoding="utf-8")
    mw.emit(target, run_id, {
        "event_type": "hitl_ack",
        "topic": topic,
        "acked_by": decided_by,
        "acked_at": decided_at,
        "outcome": outcome,
    })
    return out


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="hitl_router")
    p.add_argument("--target", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--topic", required=True)
    p.add_argument("--by", default="user")
    p.add_argument("--outcome", default="approved", choices=["approved", "rejected", "deferred"])
    p.add_argument("--notes", default=None)
    args = p.parse_args(argv)
    target = Path(args.target).resolve()
    out = ack(target, args.run_id, args.topic, args.by, args.outcome, args.notes)
    print(out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
