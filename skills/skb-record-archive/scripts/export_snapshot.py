#!/usr/bin/env python3
"""skb-record-archive export-snapshot — SQLite → Parquet (v0.12.0 skeleton)"""
import argparse, datetime, pathlib, sqlite3, sys

def main():
    ap = argparse.ArgumentParser(description="skb-record-archive export-snapshot")
    ap.add_argument("--target", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    target = pathlib.Path(args.target)
    db_path = target / "record-archive" / "runtime" / "runtime.db"
    snapshots_dir = target / "record-archive" / "snapshots"

    try:
        import duckdb
    except ImportError:
        print("duckdb 패키지가 필요합니다. pip install duckdb 를 실행해주세요.", file=sys.stderr)
        sys.exit(1)

    if not db_path.exists():
        print(f"[ERROR] runtime.db가 없습니다: {db_path}", file=sys.stderr)
        sys.exit(1)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_file = snapshots_dir / f"{timestamp}.parquet"

    print(f"[skb-record-archive export-snapshot] target={target}")
    print(f"  source: {db_path}")
    print(f"  output: {snapshot_file}")

    if not args.apply:
        print("[dry-run] --apply 없이 실행 — 스냅샷을 생성하지 않습니다.")
        return

    snapshots_dir.mkdir(parents=True, exist_ok=True)

    try:
        conn_sqlite = sqlite3.connect(db_path)
        conn_duckdb = duckdb.connect(":memory:")

        cursor = conn_sqlite.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        if not tables:
            print("[WARNING] SQLite에 테이블이 없습니다.")
            conn_sqlite.close()
            return

        for (table_name,) in tables:
            df = conn_sqlite.execute(f"SELECT * FROM {table_name}").fetchall()
            if not df:
                continue
            cursor = conn_sqlite.execute(f"SELECT * FROM {table_name} LIMIT 0")
            cols = [d[0] for d in cursor.description]
            conn_duckdb.register(table_name, df)

        conn_duckdb.execute(f"COPY (SELECT * FROM sqlite_scan('{db_path}')) TO '{snapshot_file}' (FORMAT PARQUET)")
        conn_sqlite.close()
        conn_duckdb.close()
        print(f"[skb-record-archive export-snapshot] OK → {snapshot_file}")
    except Exception as e:
        print(f"[ERROR] 스냅샷 생성 실패: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
