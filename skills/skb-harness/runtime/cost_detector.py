"""Cost mode auto-detection + per-token power estimate.

SPEC: skb-harness-SPEC §7.3, references/cost-mode-detection.md.
"""

from __future__ import annotations

import os
import re
import socket
from pathlib import Path
from urllib import error as _err
from urllib import request as _req

REF_FILE = Path(__file__).resolve().parents[1] / "references" / "power_wh_per_token.yaml"


def detect_mode(timeout: float = 1.0) -> str:
    """Return 'full' if ollama appears reachable, else 'fallback'."""
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    url = f"{host}/api/tags"
    try:
        with _req.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            if 200 <= resp.status < 300:
                return "full"
    except (_err.URLError, _err.HTTPError, TimeoutError, ConnectionError, socket.timeout, OSError, ValueError):
        pass
    return "fallback"


def _load_per_token_table() -> dict[str, float]:
    """Tiny single-file YAML parser for the `models:` and `default:` keys."""
    table: dict[str, float] = {"_default": 0.0001}
    if not REF_FILE.exists():
        return table
    text = REF_FILE.read_text(encoding="utf-8")
    m = re.search(r"^default:\s*([0-9.eE+-]+)\s*$", text, re.MULTILINE)
    if m:
        try:
            table["_default"] = float(m.group(1))
        except ValueError:
            pass
    in_models = False
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        if re.match(r"^models:\s*$", line):
            in_models = True
            continue
        if in_models:
            if line and not line.startswith(" "):
                in_models = False
                continue
            mm = re.match(r"^\s+([\w.:\-]+):\s*([0-9.eE+-]+)\s*$", line)
            if mm:
                try:
                    table[mm.group(1)] = float(mm.group(2))
                except ValueError:
                    pass
    return table


def estimate_power_wh(model: str | None, tokens: int, mode: str | None = None) -> float:
    if (mode or detect_mode()) != "full":
        return 0.0
    if tokens <= 0:
        return 0.0
    table = _load_per_token_table()
    rate = table.get(model or "", table["_default"]) if model else table["_default"]
    return round(rate * tokens, 6)
