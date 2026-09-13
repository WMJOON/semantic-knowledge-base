#!/usr/bin/env bash
# skb-explain harness wrapper.
# Delegates to the legacy skb-explain harness during migration.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEGACY="$SCRIPT_DIR/../../skb-explain/harness/run.sh"

ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill)
      ARGS+=(--skill skb-explain)
      shift 2
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

exec "$LEGACY" "${ARGS[@]}"
