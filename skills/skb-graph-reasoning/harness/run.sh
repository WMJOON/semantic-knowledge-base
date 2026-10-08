#!/usr/bin/env bash
# skb-graph-reasoning skill-level harness entrypoint.
# skb-harness 의 워크플로우 도구 실행 계약: run.sh --skill X --tier L0 --mode M --target T [--workflow W]

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

if [[ "$TIER" != "L0" ]]; then
  echo "unsupported invocation: skill=$SKILL tier=$TIER" >&2
  exit 2
fi

rc=0
"$PY" "$SCRIPTS/graph_reasoning.py" check --target "$TARGET" || rc=$?
exit $rc
