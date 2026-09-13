#!/usr/bin/env python3
"""skb-record-archive query — DuckDB parquet snapshot 분석 (v0.12.0 skeleton)"""
import argparse, json, pathlib, sys

def main():
    ap = argparse.ArgumentParser(description="skb-record-archive query")
    ap.add_argument("--target", required=True)
    ap.add_argument("--sql", required=True)
    args = ap.parse_args()

    target = pathlib.Path(args.target)
    snapshots_dir = target / "record-archive" / "snapshots"

    try:
        import duckdb
    except ImportError:
        print("duckdb 패키지가 필요합니다. pip install duckdb 를 실행해주세요.", file=sys.stderr)
        sys.exit(1)

    print(f"[skb-record-archive query] target={target}")
    print(f"  snapshots/ → {snapshots_dir}")
    print(f"  sql: {args.sql}")

    if not snapshots_dir.exists():
        print(f"[ERROR] snapshots/ 디렉토리가 없습니다: {snapshots_dir}", file=sys.stderr)
        sys.exit(1)

    parquets = list(snapshots_dir.glob("*.parquet"))
    if not parquets:
        print(f"[ERROR] parquet 파일이 없습니다: {snapshots_dir}", file=sys.stderr)
        sys.exit(1)

    conn = duckdb.connect(":memory:")
    for pq_file in parquets:
        conn.execute(f"CREATE VIEW {pq_file.stem} AS SELECT * FROM read_parquet('{pq_file}')")

    try:
        result = conn.execute(args.sql).fetchall()
        output = json.dumps([dict(zip([d[0] for d in conn.description], row)) for row in result], indent=2)
        print(output)
    except Exception as e:
        print(f"[ERROR] SQL 실행 실패: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
