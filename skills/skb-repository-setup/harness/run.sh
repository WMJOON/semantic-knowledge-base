#!/usr/bin/env bash
# skb-repository-setup skill-level harness entrypoint.
# Routes to L0 validators against an arbitrary target.

set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")" && pwd)"
L0="$HARNESS_DIR/tiers/L0_static"
PY="${PYTHON:-python3}"

SKILL=""
TIER=""
MODE=""
TARGET=""
WORKFLOW=""
STRICT=0
WITH_LINKS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill) SKILL="$2"; shift 2;;
    --tier) TIER="$2"; shift 2;;
    --mode) MODE="$2"; shift 2;;
    --target) TARGET="$2"; shift 2;;
    --workflow) WORKFLOW="$2"; shift 2;;
    --strict) STRICT=1; shift;;
    --with-skill-links) WITH_LINKS=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "missing --target" >&2
  exit 2
fi

rc=0
if [[ "$SKILL" == "skb-repository-setup" && "$TIER" == "L0" ]]; then
  "$PY" "$L0/validate_repository_setup.py" --target "$TARGET" || rc=$?
  "$PY" "$L0/validate_canonical_hub.py" --target "$TARGET" || rc=$?
  "$PY" "$L0/validate_workflows.py" --target "$TARGET" || rc=$?
  args=(--target "$TARGET")
  [[ $STRICT -eq 1 ]] && args+=(--strict)
  [[ $WITH_LINKS -eq 1 ]] && args+=(--with-skill-links)
  "$PY" "$L0/check_skill_links.py" "${args[@]}" || rc=$?
elif [[ -n "$WORKFLOW" && "$TIER" == "L0" ]]; then
  "$PY" "$L0/validate_workflows.py" --target "$TARGET" --workflow "$WORKFLOW" || rc=$?
else
  echo "unsupported invocation: skill=$SKILL tier=$TIER" >&2
  exit 2
fi

exit $rc
