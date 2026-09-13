#!/usr/bin/env python3
"""skb-record-archive insert — SQLite row 삽입 (v0.12.0 skeleton)"""
import argparse, json, pathlib, sqlite3

def main():
    ap = argparse.ArgumentParser(description="skb-record-archive insert")
    ap.add_argument("--target", required=True)
    ap.add_argument("--table", required=True)
    ap.add_argument("--data", required=True, help="JSON string")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    data = json.loads(args.data)
    db_path = pathlib.Path(args.target) / "record-archive" / "runtime" / "runtime.db"

    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" * len(data))
    sql = f"INSERT OR REPLACE INTO {args.table} ({cols}) VALUES ({placeholders})"

    print(f"[skb-record-archive insert] table={args.table} data={data}")
    if not args.apply:
        print("[dry-run] --apply 없이 실행 — insert하지 않습니다.")
        return

    conn = sqlite3.connect(db_path)
    conn.execute(sql, list(data.values()))
    conn.commit()
    conn.close()
    print("[skb-record-archive insert] OK")

if __name__ == "__main__":
    main()
