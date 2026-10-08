#!/usr/bin/env python3
"""URI fetcher for skb-evidence.

Handles:
- http/https URLs via urllib.request
- file:// URIs via urllib.request
- Local file paths (absolute or relative) → kind: "md"

Returns (kind, content_bytes, content_type, effective_uri).
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path

_DEFAULT_UA = "skb-evidence/1.0"
_MAX_RETRY = 1


def _kind_from_uri(uri: str) -> str:
    """Derive kind from URI scheme."""
    lower = uri.lower()
    if lower.startswith("http://") or lower.startswith("https://") or lower.startswith("file://"):
        return "url"
    return "md"


def fetch(
    uri: str,
    user_agent: str = _DEFAULT_UA,
    max_retry: int = _MAX_RETRY,
    timeout: int = 30,
) -> tuple[str, bytes, str, str]:
    """Fetch *uri* and return (kind, raw_bytes, content_type, effective_uri).

    Raises urllib.error.URLError / OSError on unrecoverable errors.
    """
    m = fetch_meta(uri, user_agent=user_agent, max_retry=max_retry, timeout=timeout)
    return m["kind"], m["raw"], m["content_type"], m["effective_uri"]


def fetch_meta(
    uri: str,
    user_agent: str = _DEFAULT_UA,
    max_retry: int = _MAX_RETRY,
    timeout: int = 30,
) -> dict:
    """fetch 와 같되 요청 조건을 함께 돌려준다: kind, raw, content_type, effective_uri, request_url(리다이렉트 후 최종 URL),
    method, status. 로컬 파일은 request_url·method·status 가 None 이다."""
    kind = _kind_from_uri(uri)

    if kind == "url" or uri.startswith("file://"):
        # URL-based fetch
        request = urllib.request.Request(
            uri,
            headers={"User-Agent": user_agent},
        )
        last_err: Exception | None = None
        for attempt in range(max(1, max_retry)):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as resp:
                    content_type = resp.headers.get("Content-Type", "")
                    raw = resp.read()
                    final = resp.geturl() if hasattr(resp, "geturl") else uri
                    http = final.lower().startswith(("http://", "https://"))  # file:// 은 네트워크 요청이 아니다
                    return {"kind": kind, "raw": raw, "content_type": content_type, "effective_uri": uri,
                            "request_url": final if http else None, "method": "GET" if http else None,
                            "status": getattr(resp, "status", None) if http else None}
            except Exception as exc:
                last_err = exc
        raise last_err or RuntimeError(f"Failed to fetch {uri}")

    else:
        # Local file path
        p = Path(uri)
        if not p.is_absolute():
            p = Path(os.getcwd()) / p
        raw = p.read_bytes()
        # Guess content type from extension
        suffix = p.suffix.lower()
        ct = "text/markdown" if suffix in (".md", ".markdown") else "text/plain"
        return {"kind": "md", "raw": raw, "content_type": ct, "effective_uri": p.as_uri(),
                "request_url": None, "method": None, "status": None}
