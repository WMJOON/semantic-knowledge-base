#!/usr/bin/env bash
# skb-ontology skill-level harness entrypoint.
# Routes to L0 validators against an arbitrary target.

set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HARNESS_DIR/../scripts"
PY="${PYTHON:-python3}"

SKILL=""
TIER=""
MODE=""
TARGET=""
WORKFLOW=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill)    SKILL="$2";    shift 2;;
    --tier)     TIER="$2";     shift 2;;
    --mode)     MODE="$2";     shift 2;;
    --target)   TARGET="$2";   shift 2;;
    --workflow) WORKFLOW="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "missing --target" >&2
  exit 2
fi

rc=0
if [[ "$SKILL" == "skb-ontology" && "$TIER" == "L0" ]]; then
  "$PY" "$SCRIPTS/ttl_validate.py" --target "$TARGET" || rc=$?
elif [[ -n "$WORKFLOW" && "$TIER" == "L0" ]]; then
  "$PY" "$SCRIPTS/ttl_validate.py" --target "$TARGET" || rc=$?
else
  echo "unsupported invocation: skill=$SKILL tier=$TIER" >&2
  exit 2
fi

exit $rc
