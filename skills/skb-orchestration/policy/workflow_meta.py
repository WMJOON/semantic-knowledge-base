"""Tiny workflow metadata reader used by orchestration policy modules.

Shares the same single-file approach as `skb-harness/runtime/workflow_parser.py`
but lives in orchestration so the two skills don't import each other. Reads TTL
SSOT files first, and keeps YAML fallback for both
the MSO module + x_msm format (identity under `module:`, execution under
`x_msm:`) and the legacy flat format, falling back top-level.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROUTER_DIR = Path(__file__).resolve().parents[1] / "router"
sys.path.insert(0, str(ROUTER_DIR))
from workflow_ttl import parse_workflow_ttl


def _strip_quote(s: str) -> str:
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    # unquoted scalar: drop inline comment (YAML requires whitespace before `#`;
    # a `#` glued to text like `C#` or inside quotes is preserved)
    return re.sub(r"\s+#.*$", "", s).strip()


def _block(text: str, name: str) -> str:
    """Dedented body of a top-level `name:` block, or "" if absent.

    Mirrors `workflow_parser._block` (the two skills don't import each other).
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
            break
        body.append(line)
    indents = [len(l) - len(l.lstrip()) for l in body if l.strip()]
    base = min(indents) if indents else 0
    return "\n".join(l[base:] if len(l) >= base else l for l in body)


def read_meta(path: Path) -> dict[str, Any]:
    if path.suffix == ".ttl":
        return parse_workflow_ttl(path)

    text = path.read_text(encoding="utf-8")
    xmsm = _block(text, "x_msm")
    module = _block(text, "module")
    out: dict[str, Any] = {}

    # identity → module block (else top-level); execution → x_msm block (else top-level)
    sources = {
        "version": (module,),
        "id": (module,),
        "category": (xmsm,),
        "kind": (xmsm,),
        "mode": (xmsm,),
        "status": (xmsm, module),
        "tool": (xmsm,),
    }
    for fname, blocks in sources.items():
        for b in (*blocks, text):
            if not b:
                continue
            m = re.search(rf"^{re.escape(fname)}:\s*([^\n]+)\s*$", b, re.MULTILINE)
            if m:
                out[fname] = _strip_quote(m.group(1))
                break

    gov_src = xmsm or text
    gov: dict[str, Any] = {}
    for key in ("oracle", "oracle_threshold", "max_retry"):
        m = re.search(rf"^\s+{re.escape(key)}:\s*([^\n]+)\s*$", gov_src, re.MULTILINE)
        if m:
            v = _strip_quote(m.group(1))
            if v.lower() == "null":
                gov[key] = None
            else:
                try:
                    gov[key] = float(v) if "." in v else int(v)
                except ValueError:
                    gov[key] = v
    if gov:
        out["governance"] = gov
    return out
