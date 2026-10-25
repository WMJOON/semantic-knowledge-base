"""자주 묻는 SPARQL 템플릿: 질문으로 템플릿을 찾고, IRI 슬롯만 채워 읽기 전용으로 실행한다.

템플릿 파일: references/sparql-templates.json
- 각 템플릿은 질문 예시(questions), 설명(description), 슬롯 종류(slots), 쿼리(sparql)를 가진다.
- 슬롯은 <<NAME>> 으로 쓰고, 값은 IRI 로만 들어간다. 문자열 치환으로 IRI 를 쓰므로 쿼리 구조는 바뀌지 않는다.
- 슬롯 종류: class(클래스 IRI), property(속성 IRI), instance(개체 IRI, q: 검색 불가)
- 값이 q:텍스트 이면 TBox 라벨 키워드 검색 1순위의 IRI 를 쓴다. 후보 목록도 함께 돌려준다.
- 실행은 SELECT 만 허용한다. 쓰기 키워드가 있으면 실행하지 않는다.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

import ss_common as C
import ss_hybrid as H

TEMPLATE_FILE = Path(__file__).resolve().parents[1] / "references" / "sparql-templates.json"
SLOT_RE = re.compile(r"<<([A-Z][A-Z0-9_]*)>>")
WRITE_RE = re.compile(r"\b(INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|ADD|MOVE|COPY)\b", re.I)
IRI_RE = re.compile(r"^(https?://|urn:)[^\s<>\"]+$")
SLOT_KINDS = ("class", "property", "instance")


def load_templates(path: Path = TEMPLATE_FILE) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["templates"]


def slots_of(t: dict) -> list[str]:
    return list(dict.fromkeys(SLOT_RE.findall(t["sparql"])))


def validate_template(t: dict) -> list[str]:
    errs = []
    for key in ("id", "questions", "description", "slots", "sparql"):
        if key not in t:
            errs.append(f"{t.get('id', '?')}: '{key}' 없음")
    if errs:
        return errs
    bad_kinds = [k for k, v in t["slots"].items() if v not in SLOT_KINDS]
    if bad_kinds:
        errs.append(f"{t['id']}: 알 수 없는 슬롯 종류 {bad_kinds}")
    used, declared = set(slots_of(t)), set(t["slots"])
    if used - declared:
        errs.append(f"{t['id']}: 선언되지 않은 슬롯 {sorted(used - declared)}")
    if declared - used:
        errs.append(f"{t['id']}: 쿼리에서 쓰이지 않는 슬롯 {sorted(declared - used)}")
    try:
        assert_read_only(t["sparql"])
    except ValueError as e:
        errs.append(f"{t['id']}: {e}")
    return errs


def assert_read_only(query: str) -> None:
    if WRITE_RE.search(query):
        raise ValueError("쓰기 키워드가 있어 실행하지 않는다")
    if not re.search(r"\bSELECT\b", query, re.I):
        raise ValueError("SELECT 쿼리가 아니다")


def template_side(t: dict) -> dict:
    return {"label": " / ".join(t["questions"]), "alt": [], "hidden": [], "note": t.get("description", "")}


def search_templates(query: str, templates: list[dict], k: int = 5) -> list[dict]:
    docs = {t["id"]: H.bm25_tokens(template_side(t)) for t in templates}
    by_id = {t["id"]: t for t in templates}
    return [by_id[i] for i in H.Bm25(docs).rank(query, limit=k)]


def to_iri(value: str) -> str:
    if not IRI_RE.match(value):
        raise ValueError(f"IRI 가 아니다: {value}")
    return f"<{value}>"


def fill(t: dict, bindings: dict[str, str]) -> str:
    missing = [s for s in slots_of(t) if s not in bindings]
    if missing:
        raise ValueError(f"슬롯이 채워지지 않았다: {missing}")
    return SLOT_RE.sub(lambda m: to_iri(bindings[m.group(1)]), t["sparql"])


def tbox_side(r: dict) -> dict:
    names = list(r.get("pref_en") or []) + list(r.get("pref_ko") or [])
    return {"label": " / ".join(names), "alt": list(r.get("alt") or []),
            "hidden": list(r.get("hidden") or []), "note": r.get("note") or ""}


norm_label = H.norm_label


def resolve_tbox(text: str, tbox_rows: list[dict], kind: str, limit: int = 5) -> tuple[str, list[str]]:
    """q:텍스트 를 kind(class|property) 의 IRI 로 바꾼다. 1순위 IRI 와 후보 목록을 돌려준다.

    정확 일치(정규화 후 같은 라벨·대체 라벨·숨은 라벨)가 있으면 키워드 점수보다 먼저 쓴다.
    """
    cands = [r for r in tbox_rows if r.get("tkind") == kind]
    q = norm_label(text)
    exact = [r["iri"] for r in cands
             if q and any(norm_label(x) == q for x in (list(r.get("pref_en") or []) + list(r.get("pref_ko") or [])
                                                      + list(r.get("alt") or []) + list(r.get("hidden") or [])))]
    docs = {r["iri"]: H.bm25_tokens(tbox_side(r)) for r in cands}
    ranked = list(dict.fromkeys(exact + H.Bm25(docs).rank(text, limit=limit)))[:limit]
    if not ranked:
        raise ValueError(f"'{text}' 에 맞는 {kind} 가 없다")
    return ranked[0], ranked


def load_graph(target: Path):
    """KB 의 의미 TTL 을 하나의 rdflib 그래프로 읽는다. 파싱 실패 파일 목록을 함께 돌려준다."""
    from rdflib import Graph
    g, failed = Graph(), []
    for f in C.semantic_ttl_files(target):
        try:
            g.parse(f, format="turtle")
        except Exception as e:  # 실패는 숨기지 않고 호출자가 보고한다
            failed.append(f"{C.rel_to(target, f)} ({type(e).__name__})")
    return g, failed


def run_select(g, query: str) -> dict:
    assert_read_only(query)
    res = g.query(query)
    return {"vars": [str(v) for v in res.vars],
            "rows": [[str(x) if x is not None else None for x in row] for row in res]}
