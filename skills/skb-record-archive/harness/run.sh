#!/usr/bin/env bash
# skb-record-archive skill-level harness entrypoint.
# Routes to L0 validators against an arbitrary target.

set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"

SKILL=""
TIER=""
MODE=""
TARGET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill) SKILL="$2"; shift 2;;
    --tier) TIER="$2"; shift 2;;
    --mode) MODE="$2"; shift 2;;
    --target) TARGET="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "missing --target" >&2
  exit 2
fi

if [[ "$SKILL" == "skb-record-archive" && "$TIER" == "L0" && "$MODE" == "validate-only" ]]; then
  RUNTIME_DB="$TARGET/record-archive/runtime/runtime.db"
  if [[ ! -f "$RUNTIME_DB" ]]; then
    echo "[ERROR] runtime.db not found: $RUNTIME_DB" >&2
    exit 1
  fi
  echo "[skb-record-archive L0 validate] OK: $RUNTIME_DB exists"
else
  echo "unsupported invocation: skill=$SKILL tier=$TIER mode=$MODE" >&2
  exit 2
fi
