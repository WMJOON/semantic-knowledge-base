#!/usr/bin/env python3
"""수집(Retrieval) 기록 도우미 — 시점·요청 조건을 seed/원문 frontmatter 에 일관되게 남긴다.

시점은 세 가지다(카탈로그 ec:Retrieval): searched_at(검색으로 찾은 경우만, 질의 필수) / retrieved_at(내려받은 시각, seed 최상위)
/ collected_at(적재 시작, 원문 frontmatter). 이 모듈은 searched_at·요청 조건을 다룬다. 추정하지 않고 도구가 본 값만 기록한다.
"""
from __future__ import annotations

import hashlib
import json
import re

_ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# frontmatter 에 싣는 키(원문 노트 → collect 가 같은 이름으로 seed.retrieval 에 옮긴다). 로컬 중간 파일 한정으로 신뢰한다.
FM_KEYS = ("request_url", "media_type", "response_sha256", "searched_at", "search_query", "request_params")


def media_type(content_type: str | None) -> str | None:
    """'text/html; charset=utf-8' → 'text/html'."""
    if not content_type:
        return None
    return content_type.split(";", 1)[0].strip().lower() or None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_search(searched_at: str | None, search_query: str | None) -> str | None:
    """검색 인자 검증. 문제가 있으면 사유 문자열, 없으면 None. 검색 시각은 질의와 함께만 쓴다."""
    if searched_at is None and search_query is None:
        return None
    if not searched_at or not search_query:
        return "--searched-at 과 --search-query 는 함께 써야 한다(검색으로 찾았다면 어떤 질의인지 남긴다)"
    if not _ISO_Z.match(searched_at):
        return f"--searched-at 은 UTC ISO(YYYY-MM-DDTHH:MM:SSZ)여야 한다: {searched_at!r}"
    return None


def check_params(raw: str | None) -> tuple[dict | None, str | None]:
    if raw is None:
        return None, None
    try:
        v = json.loads(raw)
    except ValueError:
        return None, f"--request-params 는 JSON 객체여야 한다: {raw!r}"
    if not isinstance(v, dict):
        return None, f"--request-params 는 JSON 객체여야 한다: {raw!r}"
    return v, None


def clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "", {})}


def retrieval_from_fetch(meta: dict, raw: bytes, search: dict | None, params: dict | None) -> dict:
    """fetcher.fetch_meta 결과에서 seed.retrieval 을 만든다. http(s) 요청이면 최종 URL·상태·방식을 기록한다."""
    out = {"media_type": media_type(meta.get("content_type")), "response_sha256": sha256_hex(raw)}
    if meta.get("request_url"):  # http(s)/file URL 요청
        out.update({"request_url": meta["request_url"], "method": meta.get("method"), "status": meta.get("status")})
    if search:
        out.update(search)
    if params:
        out["params"] = params
    return clean(out)


def retrieval_from_frontmatter(fm: dict[str, str], search: dict | None, params: dict | None) -> dict:
    """convert 가 쓴 원문 노트 frontmatter 에서 seed.retrieval 을 만든다(로컬 중간 파일 한정). CLI 인자가 우선한다."""
    out = {k: fm[k] for k in ("request_url", "media_type", "response_sha256", "searched_at", "search_query") if fm.get(k)}
    if fm.get("request_params"):
        try:
            v = json.loads(fm["request_params"])
            if isinstance(v, dict):
                out["params"] = v
        except ValueError:
            pass
    if search:
        out.update(search)
    if params:
        out["params"] = params
    return clean(out)


def problems(retrieval: dict, retrieved_at: str | None) -> list[str]:
    """seed.retrieval 의 형식·일관성 위반(verify 가 쓴다)."""
    out: list[str] = []
    if not isinstance(retrieval, dict):
        return ["retrieval 은 객체여야 한다"]
    s, q = retrieval.get("searched_at"), retrieval.get("search_query")
    if (s is None) != (q is None):
        out.append("retrieval.searched_at 과 search_query 는 함께 있어야 한다")
    if s is not None and not _ISO_Z.match(str(s)):
        out.append(f"retrieval.searched_at 형식 오류 ({s!r})")
    if s is not None and retrieved_at and _ISO_Z.match(str(s)) and _ISO_Z.match(retrieved_at) and s > retrieved_at:
        out.append(f"retrieval.searched_at({s})이 retrieved_at({retrieved_at})보다 늦다")
    h = retrieval.get("response_sha256")
    if h is not None and not _HEX64.match(str(h)):
        out.append(f"retrieval.response_sha256 형식 오류 ({h!r})")
    m = retrieval.get("method")
    if m is not None and m not in ("GET", "POST"):
        out.append(f"retrieval.method 은 GET|POST ({m!r})")
    st = retrieval.get("status")
    if st is not None and not isinstance(st, int):
        out.append(f"retrieval.status 는 정수 ({st!r})")
    return out
