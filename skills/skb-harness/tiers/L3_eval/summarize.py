#!/usr/bin/env python3
"""L3 eval — trajectory aggregation report.

Reads all run-*.jsonl files for the given target and produces a markdown
summary in harness/reports/eval-<timestamp>.md. Cost / oracle / HITL stats.

Initial scope: tabulate runs, no answer-key comparison yet (HRN-OI-3).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="l3.summarize")
    ap.add_argument("--target", required=True)
    args = ap.parse_args(argv)
    target = Path(args.target).resolve()
    traj_dir = target / "harness" / "trajectory"
    if not traj_dir.is_dir():
        print(f"no trajectory dir at {traj_dir}", file=sys.stderr)
        return 1
    rows: list[dict] = []
    for jf in sorted(traj_dir.glob("run-*.jsonl")):
        meas = None
        finished = None
        started = None
        for line in jf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event_type") == "run_started":
                started = ev
            elif ev.get("event_type") == "governance_measurement":
                meas = ev
            elif ev.get("event_type") == "run_finished":
                finished = ev
        if not started:
            continue
        rows.append({
            "run_id": started["run_id"],
            "workflow_id": started.get("workflow_id"),
            "skill": started.get("skill"),
            "tier": started.get("tier"),
            "mode": started.get("mode"),
            "exit_code": (finished or {}).get("exit_code"),
            "duration_seconds": (finished or {}).get("duration_seconds"),
            "oracle_score": (meas or {}).get("oracle_score"),
            "cost": (meas or {}).get("cost"),
            "hitl": (meas or {}).get("hitl"),
        })
    reports = target / "harness" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = reports / f"eval-{ts}.md"
    lines = [
        "<!-- msm:generated:file skill=\"skb-harness\" version=\"1.0.0\" -->",
        f"# Harness Eval Report — {ts}",
        "",
        f"Runs analysed: {len(rows)}",
        "",
        "| run_id | tier | mode | exit | duration | oracle | hitl | cost.mode | tokens |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        c = r.get("cost") or {}
        h = r.get("hitl") or {}
        lines.append(
            f"| {r['run_id']} | {r['tier']} | {r['mode']} | {r['exit_code']} | "
            f"{r['duration_seconds']} | {r['oracle_score']} | "
            f"{h.get('acked',0)}/{h.get('requested',0)} | "
            f"{c.get('mode','')} | {c.get('tokens',0)} |"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
