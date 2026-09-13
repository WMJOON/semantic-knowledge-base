#!/usr/bin/env python3
"""skb-record-archive migrate — SQLite schema 마이그레이션 (v0.12.0 skeleton)"""
import argparse, pathlib, sqlite3, sys

def main():
    ap = argparse.ArgumentParser(description="skb-record-archive migrate")
    ap.add_argument("--target", required=True)
    ap.add_argument("--to", required=True, help="target version")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    target = pathlib.Path(args.target)
    schema_dir = target / "record-archive" / "schema"
    migrate_file = schema_dir / f"migrate_{args.to}.sql"
    db_path = target / "record-archive" / "runtime" / "runtime.db"

    print(f"[skb-record-archive migrate] target={target} to={args.to}")
    print(f"  migration → {migrate_file}")

    if not migrate_file.exists():
        print(f"[ERROR] 마이그레이션 파일이 없습니다: {migrate_file}", file=sys.stderr)
        sys.exit(1)

    if not db_path.exists():
        print(f"[ERROR] runtime.db가 없습니다: {db_path}", file=sys.stderr)
        sys.exit(1)

    migration_sql = migrate_file.read_text()
    print(f"[dry-run] 다음 SQL을 실행합니다:\n{migration_sql}")

    if not args.apply:
        print("[dry-run] --apply 없이 실행 — 마이그레이션하지 않습니다.")
        return

    try:
        conn = sqlite3.connect(db_path)
        conn.executescript(migration_sql)
        conn.commit()
        conn.close()
        print("[skb-record-archive migrate] OK")
    except Exception as e:
        print(f"[ERROR] 마이그레이션 실패: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
