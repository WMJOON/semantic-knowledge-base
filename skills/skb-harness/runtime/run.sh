#!/usr/bin/env bash
# skb-harness entrypoint. Delegates to dispatch.py.
set -euo pipefail
RUNTIME_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${PYTHON:-python3}" "$RUNTIME_DIR/dispatch.py" "$@"
