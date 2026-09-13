#!/usr/bin/env python3
"""PreToolUse hook.

SPEC §8. Reads a Claude Code PreToolUse payload on stdin (JSON), checks the
affected paths against `hitl-policy.yaml::pretool_block_patterns`, and exits
non-zero with a structured reason if any pattern matches.

`MSM_HOOKS_DISABLED=1` bypasses (audit: caller logs `hooks_disabled` itself).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from pathlib import Path

SKILL_HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_HOME / "router"))

import _yaml_lite as yaml  # noqa: E402


def _payload_paths(payload: dict) -> list[str]:
    """Extract candidate file paths from a Claude Code tool-call payload.

    Tool payloads vary (Edit, Write, Bash...). We sweep common fields.
    """
    paths: list[str] = []
    fields = ("file_path", "path", "filepath", "target_file")
    tool_input = payload.get("tool_input") or payload.get("input") or payload
    if isinstance(tool_input, dict):
        for f in fields:
            v = tool_input.get(f)
            if isinstance(v, str):
                paths.append(v)
        # Bash command path extraction (cheap heuristic)
        cmd = tool_input.get("command")
        if isinstance(cmd, str):
            for m in re.finditer(r"\s([^\s]+\.(?:yaml|jsonl|md|py|sh))", cmd):
                paths.append(m.group(1))
    return paths


def _match(path: str, glob: str) -> bool:
    # `glob` can be repo-relative or anchored; we test against both raw and basename.
    if fnmatch.fnmatch(path, glob):
        return True
    # Path globs like "ontology/explain/concept/**/*.jsonl"
    if "**" in glob:
        pattern = re.escape(glob).replace(r"\*\*", ".*").replace(r"\*", "[^/]*").replace(r"\?", ".")
        return re.search(pattern + "$", path) is not None
    return False


def evaluate(payload: dict, policy: dict) -> dict:
    paths = _payload_paths(payload)
    patterns = policy.get("pretool_block_patterns", []) or []
    for path in paths:
        for pat in patterns:
            if _match(path, pat["path_glob"]):
                return {
                    "blocked": True,
                    "reason": pat.get("reason"),
                    "target": path,
                    "proposed_action": pat.get("proposed_action"),
                    "matched_pattern": pat["path_glob"],
                }
    return {"blocked": False}


def main() -> int:
    if os.environ.get("MSM_HOOKS_DISABLED") == "1":
        return 0
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    policy_path = SKILL_HOME / "references" / "hitl-policy.yaml"
    policy = yaml.load(policy_path)
    verdict = evaluate(payload, policy)
    if verdict["blocked"]:
        sys.stderr.write("skb-orchestration: blocked by always_hitl policy\n")
        sys.stderr.write(f"  reason: {verdict['reason']}\n")
        sys.stderr.write(f"  target: {verdict['target']}\n")
        sys.stderr.write(f"  proposed_action: {verdict['proposed_action']}\n")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
