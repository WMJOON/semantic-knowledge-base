#!/usr/bin/env python3
"""skb-maintain report — generate troubleshooting report for a date range.

Saves to agent-context/work-memory/insight-record/<run_id>__report.md.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

TOOL_VERSION = "skb-maintain/1.0.0"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="report")
    p.add_argument("--target", required=True)
    p.add_argument("--since", required=True, help="YYYY-MM-DD")
    p.add_argument("--run-id", default=None, dest="run_id")
    return p.parse_args(argv)


def _run_id_or_new(val: str | None) -> str:
    if val:
        return val
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_trajectory_events(target: Path, since: _dt.date) -> list[dict]:
    """Load all trajectory events from all run-*.jsonl files since given date."""
    traj_dir = target / "harness" / "trajectory"
    events: list[dict] = []
    if not traj_dir.exists():
        return events
    for f in sorted(traj_dir.glob("run-*.jsonl")):
        for line in f.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_str = ev.get("ts", "")
            if ts_str:
                try:
                    ev_date = _dt.date.fromisoformat(ts_str[:10])
                    if ev_date >= since:
                        events.append(ev)
                except ValueError:
                    events.append(ev)
            else:
                events.append(ev)
    return events


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    target = Path(args.target).resolve()
    run_id = _run_id_or_new(args.run_id)

    try:
        since_date = _dt.date.fromisoformat(args.since)
    except ValueError:
        print(f"ERROR: --since must be YYYY-MM-DD, got: {args.since!r}", file=sys.stderr)
        return 1

    events = _load_trajectory_events(target, since_date)
    scan_events = [e for e in events if e.get("event_type") == "scan_complete"]

    ts = _dt.datetime.now(tz=_dt.timezone.utc).isoformat()
    lines = [
        f'<!-- msm:generated:file skill="skb-maintain" version="1.0.0" -->',
        f"# Maintain Report — {target.name}",
        "",
        f"**Since**: {args.since}  ",
        f"**Generated**: {ts}  ",
        f"**Target**: `{target}`  ",
        "",
        f"## Scan Events ({len(scan_events)})",
        "",
    ]

    if not scan_events:
        lines.append("No scan events found in the specified date range.")
    else:
        for ev in scan_events:
            lines += [
                f"### Run: `{ev.get('run_id', '?')}`",
                "",
                f"- Timestamp: {ev.get('ts', '?')}",
                f"- Plan ID: `{ev.get('plan_id', '?')}`",
                f"- Drift findings: {ev.get('drift_count', '?')}",
                f"- Orphan findings: {ev.get('orphan_count', '?')}",
                f"- Auto-fixes: {ev.get('auto_fixes_count', '?')}",
                "",
            ]

    lines += [
        "## Summary",
        "",
        f"- Total scan runs: {len(scan_events)}",
        f"- Total drift events: {sum(e.get('drift_count', 0) for e in scan_events)}",
        f"- Total orphan events: {sum(e.get('orphan_count', 0) for e in scan_events)}",
        "",
    ]

    report_text = "\n".join(lines)

    # Save report
    log_dir = target / "agent-context" / "work-memory" / "insight-record"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{run_id}__report.md"
    log_path.write_text(report_text, encoding="utf-8")

    print(report_text)
    print(f"\n[report] Saved: {log_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
