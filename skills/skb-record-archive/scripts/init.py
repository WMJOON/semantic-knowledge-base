#!/usr/bin/env python3
"""skb-record-archive init — SQLite runtime.db 초기화 (v0.12.0 skeleton)"""
import argparse, pathlib, sqlite3, sys

DDL = """
CREATE TABLE IF NOT EXISTS market_signal (
    signal_id TEXT PRIMARY KEY,
    value REAL NOT NULL,
    source TEXT,
    archived_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS eca_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT,
    row_json TEXT,
    rule_id TEXT,
    action TEXT,
    fired_at TEXT DEFAULT (datetime('now'))
);
"""

def main():
    ap = argparse.ArgumentParser(description="skb-record-archive init")
    ap.add_argument("--target", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    target = pathlib.Path(args.target)
    archive_dir = target / "record-archive"
    runtime_dir = archive_dir / "runtime"
    db_path = runtime_dir / "runtime.db"
    snapshots_dir = archive_dir / "snapshots"
    registry_dir = archive_dir / "registry"
    events_dir = archive_dir / "events"
    derived_dir = archive_dir / "derived"
    schema_dir = archive_dir / "schema"

    print(f"[skb-record-archive init] target={target}")
    print(f"  runtime.db  → {db_path}")
    print(f"  snapshots/  → {snapshots_dir}")

    if not args.apply:
        print("[dry-run] --apply 없이 실행 — 파일을 생성하지 않습니다.")
        return

    for path in (registry_dir, runtime_dir, events_dir, derived_dir, snapshots_dir, schema_dir):
        path.mkdir(parents=True, exist_ok=True)
    (registry_dir / "instance-ids.jsonl").touch(exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.executescript(DDL)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.commit()
    conn.close()
    print("[skb-record-archive init] OK")

if __name__ == "__main__":
    main()
