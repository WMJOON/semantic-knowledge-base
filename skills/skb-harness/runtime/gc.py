#!/usr/bin/env python3
"""Run context GC.

SPEC: skb-harness-SPEC §5.3. Archive runs that closed >7d ago, drop
archives that are >30d old. Designed to be called from cron / launchd.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sys
import tarfile
from pathlib import Path


ACTIVE_TTL_DAYS = 7
ARCHIVE_TTL_DAYS = 30


def _is_closed(active_run: Path) -> bool:
    """A run is considered closed when its work-log mirror exists or there's
    a `run_finished` event in trajectory."""
    repo = active_run.parents[2]  # active/<id>/ -> repo
    run_id = active_run.name
    if (repo / "memory" / "task-context" / "work-log" / f"{run_id}.md").exists():
        return True
    traj = repo / "harness" / "trajectory" / f"run-{run_id}.jsonl"
    if traj.exists() and '"event_type":"run_finished"' in traj.read_text(encoding="utf-8", errors="ignore"):
        return True
    return False


def _age_days(p: Path) -> float:
    mtime = _dt.datetime.fromtimestamp(p.stat().st_mtime, tz=_dt.timezone.utc)
    delta = _dt.datetime.now(tz=_dt.timezone.utc) - mtime
    return delta.total_seconds() / 86400.0


def archive_active(repo: Path) -> list[Path]:
    archived: list[Path] = []
    active_root = repo / ".msm-context" / "active"
    if not active_root.is_dir():
        return archived
    archive_root = repo / ".msm-context" / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    for slot in active_root.iterdir():
        if not slot.is_dir() or slot.name.startswith("."):
            continue
        if not _is_closed(slot):
            continue
        if _age_days(slot) < ACTIVE_TTL_DAYS:
            continue
        # date-based subdir from slot name (YYYYMMDDT...)
        sub = archive_root / slot.name[:4] / slot.name[4:6]
        sub.mkdir(parents=True, exist_ok=True)
        out = sub / f"{slot.name}.tar.gz"
        with tarfile.open(out, "w:gz") as tar:
            tar.add(slot, arcname=slot.name)
        shutil.rmtree(slot)
        archived.append(out)
    return archived


def gc_archives(repo: Path) -> list[Path]:
    dropped: list[Path] = []
    archive_root = repo / ".msm-context" / "archive"
    if not archive_root.is_dir():
        return dropped
    for tgz in archive_root.rglob("*.tar.gz"):
        if _age_days(tgz) >= ARCHIVE_TTL_DAYS:
            tgz.unlink()
            dropped.append(tgz)
    return dropped


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="harness.gc")
    ap.add_argument("--target", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    repo = Path(args.target).resolve()
    if args.dry_run:
        # Walk only; do nothing destructive.
        active = repo / ".msm-context" / "active"
        if active.is_dir():
            for slot in active.iterdir():
                if slot.is_dir() and _is_closed(slot) and _age_days(slot) >= ACTIVE_TTL_DAYS:
                    print(f"would-archive: {slot}")
        arc = repo / ".msm-context" / "archive"
        if arc.is_dir():
            for tgz in arc.rglob("*.tar.gz"):
                if _age_days(tgz) >= ARCHIVE_TTL_DAYS:
                    print(f"would-drop: {tgz}")
        return 0
    arch = archive_active(repo)
    drop = gc_archives(repo)
    print(f"archived={len(arch)} dropped={len(drop)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
