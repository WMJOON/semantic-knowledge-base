#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0

if rg -l -I \
  -e '/Users/[^/[:space:]"`]+' \
  -e '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' \
  -e 'tail[0-9a-f]+\.ts\.net' \
  --glob '!scripts/public_release_audit.sh' \
  . >/dev/null; then
  echo "FAIL: personal path, email, or private host pattern found" >&2
  fail=1
fi

if rg -l -I \
  -e '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----' \
  -e 'github_pat_[A-Za-z0-9_]{20,}' \
  -e 'gh[pousr]_[A-Za-z0-9]{20,}' \
  -e 'AKIA[0-9A-Z]{16}' \
  -e 'ASIA[0-9A-Z]{16}' \
  -e 'xox[baprs]-[A-Za-z0-9-]{10,}' \
  -e 'sk-[A-Za-z0-9_-]{20,}' \
  -e 'AIza[0-9A-Za-z_-]{30,}' \
  -e 'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}' \
  --glob '!scripts/public_release_audit.sh' \
  . >/dev/null; then
  echo "FAIL: credential or token pattern found" >&2
  fail=1
fi

legacy=(
  skills/skb-ontology/scripts/compile.py
  skills/skb-ontology/scripts/abox_compile.py
  skills/skb-ontology/scripts/add.py
  skills/skb-ontology/scripts/materialize.py
  skills/skb-ontology/scripts/reason.py
  skills/skb-ontology/scripts/project_md.py
  graph-ontology.example.yaml
)
for path in "${legacy[@]}"; do
  if [[ -e "$path" ]]; then
    echo "FAIL: retired ontology path is public: $path" >&2
    fail=1
  fi
done

if find agent-context/work-memory -type f ! -name index.md -print -quit | grep -q .; then
  echo "FAIL: work-memory record included in public source" >&2
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi

echo "PASS: public privacy and TTL-only boundary"
