"""Minimal parser for the subset of workflow metadata we consume.

TTL is the SSOT. YAML remains a migration/edit layer, and the YAML fallback
keeps the old text parser because we only read a handful of fields
(kind, tool, pipeline, governance.*).

Two formats are supported, newest first:
  · MSO module + x_msm — structure lives under `module:`/named phases (consumed
    by MSO mso-workflow-design); MSM's execution contract lives under `x_msm:`
    (category/kind/mode/tool/pipeline/governance). We read identity from
    `module:` and execution from `x_msm:`.
  · legacy flat ETL — every field at top level. Used by un-converted workflows.
Reads fall back top-level so both formats parse with the same call.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from workflow_ttl import parse_workflow_ttl


def _strip_quote(s: str) -> str:
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    # unquoted scalar: drop inline comment (YAML requires whitespace before `#`;
    # a `#` glued to text like `C#` or inside quotes is preserved)
    return re.sub(r"\s+#.*$", "", s).strip()


def _block(text: str, name: str) -> str:
    """Return the dedented body of a top-level `name:` block, or "" if absent.

    The header sits at column 0; the body is the following lines indented past
    column 0, up to the next column-0 line. Dedenting by the block's minimal
    indent lets the flat-key regexes below match block children unchanged.
    """
    m = re.search(rf"^{re.escape(name)}:[^\n]*\n", text, re.MULTILINE)
    if not m:
        return ""
    body: list[str] = []
    for line in text[m.end():].splitlines():
        if line.strip() == "":
            body.append(line)
            continue
        if not line[:1].isspace():
            break  # column-0 non-blank (next key or comment) → block ended
        body.append(line)
    indents = [len(l) - len(l.lstrip()) for l in body if l.strip()]
    base = min(indents) if indents else 0
    return "\n".join(l[base:] if len(l) >= base else l for l in body)


def parse(path: Path) -> dict[str, Any]:
    if path.suffix == ".ttl":
        return parse_workflow_ttl(path)

    text = path.read_text(encoding="utf-8")
    out: dict[str, Any] = {"path": str(path), "raw": text}

    xmsm = _block(text, "x_msm")     # MSM execution contract (MSO+x_msm format)
    module = _block(text, "module")  # MSO structural identity

    def field(name: str, *blocks: str) -> str | None:
        """first `^name:` scalar across the given blocks, else top-level text."""
        for b in (*blocks, text):
            if not b:
                continue
            m = re.search(rf"^{re.escape(name)}:\s*([^\n]+)\s*$", b, re.MULTILINE)
            if m:
                return _strip_quote(m.group(1))
        return None

    out["version"] = field("version", module)
    out["id"] = field("id", module)
    out["category"] = field("category", xmsm)
    out["kind"] = field("kind", xmsm)
    out["mode"] = field("mode", xmsm)
    out["status"] = field("status", xmsm, module)
    out["tool"] = field("tool", xmsm)

    # governance block: scan a few specific keys (x_msm.governance, else top-level)
    gov_src = xmsm or text
    gov: dict[str, Any] = {}
    for key in ("hitl_required", "max_retry", "oracle", "oracle_threshold"):
        m = re.search(rf"^\s+{re.escape(key)}:\s*([^\n]+)\s*$", gov_src, re.MULTILINE)
        if m:
            v = _strip_quote(m.group(1))
            if key in ("hitl_required",):
                gov[key] = v.lower() == "true"
            elif key in ("max_retry",):
                try:
                    gov[key] = int(v)
                except ValueError:
                    gov[key] = 1
            elif key == "oracle_threshold":
                try:
                    gov[key] = float(v)
                except ValueError:
                    gov[key] = 0.85
            else:
                gov[key] = v if v.lower() != "null" else None
    out["governance"] = gov

    # cost_budget (best-effort)
    budget: dict[str, Any] = {}
    for key in ("tokens", "seconds", "power_wh"):
        m = re.search(rf"^\s+{re.escape(key)}:\s*([^\n]+)\s*$", gov_src, re.MULTILINE)
        if m:
            v = _strip_quote(m.group(1))
            if v.lower() == "null":
                budget[key] = None
            else:
                try:
                    budget[key] = float(v) if "." in v else int(v)
                except ValueError:
                    pass
    if budget:
        out["cost_budget"] = budget

    # pipeline steps (x_msm.pipeline in MSO+x_msm format, else top-level)
    pipe_src = xmsm or text
    steps: list[dict[str, Any]] = []
    m_pipe = re.search(r"^pipeline:\s*\n((?:(?:[ \t]+[^\n]*|^[ \t]*-[^\n]*)\n)+)", pipe_src, re.MULTILINE)
    if m_pipe:
        block = m_pipe.group(1)
        cur: dict[str, Any] = {}
        for raw_line in block.splitlines():
            if not raw_line.strip():
                continue
            if re.match(r"^\s*-\s", raw_line):
                if cur:
                    steps.append(cur)
                cur = {}
                inline = re.match(r"^\s*-\s*([\w]+):\s*([^\n]+)\s*$", raw_line)
                if inline:
                    cur[inline.group(1)] = _strip_quote(inline.group(2))
                continue
            kv = re.match(r"^\s+([\w]+):\s*([^\n]+)\s*$", raw_line)
            if kv:
                cur[kv.group(1)] = _strip_quote(kv.group(2))
        if cur:
            steps.append(cur)
    out["pipeline"] = steps
    return out
