#!/usr/bin/env bash
# skb-semantic-search skill-level harness entrypoint.
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
# 인덱스가 아직 없거나 오래됐으면 status 가 1 을 돌려준다. L0 정적 단계에서는 도구가 돌고 상태를 보고하면 통과로 보고, 2 이상(오류)만 실패다.
"$PY" "$SCRIPTS/semantic_search.py" status --target "$TARGET" || rc=$?
if [[ $rc -eq 1 ]]; then
  echo "NOTE: 인덱스가 fresh 가 아니다 (재색인은 별도 단계)" >&2
  rc=0
fi
exit $rc
