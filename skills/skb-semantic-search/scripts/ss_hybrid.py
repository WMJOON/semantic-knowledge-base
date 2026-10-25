"""하이브리드 검색과 TBox 확장의 순수 함수. zvec 과 rdflib 없이 테스트할 수 있게 분리했다.

- tokenize: 영문·숫자 단어와 한글 어절(3글자 이상은 2-gram 추가)
- Bm25: 필드 가중치를 반복으로 준 BM25 키워드 색인 (라벨 3회, 대체·숨은 라벨 2회, 정의 1회)
- rrf_fuse: 상호 순위 결합 (벡터 순위와 키워드 순위를 합침)
- concept_match: concept_filter 와 같은 조건을 파이썬에서 적용 (키워드 후보 필터)
- tbox_doc / side_entry: 벡터 입력 텍스트, zvec 필드, 키워드 색인 항목
- expand_tbox: 검색 hit 에서 domain·range·상하위 관계를 따라 스키마 요소를 덧붙인다
"""
from __future__ import annotations
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

RRF_K = 60
BM25_K1 = 1.2
BM25_B = 0.75
TEXTS_NAME = "texts_{kind}.jsonl"
_WORD = re.compile(r"[a-z0-9]+|[가-힣]+")
_HANGUL = re.compile(r"[가-힣]+")


def texts_path(store_dir: Path, kind: str) -> Path:
    return store_dir / TEXTS_NAME.format(kind=kind)


def tokenize(text: str) -> list[str]:
    toks: list[str] = []
    for w in _WORD.findall((text or "").lower()):
        toks.append(w)
        if _HANGUL.fullmatch(w) and len(w) >= 3:
            toks.extend(w[i:i + 2] for i in range(len(w) - 1))
    return toks


def concept_match(row: dict, statuses=None, include_deprecated=False, scheme=None) -> bool:
    """ss_common.concept_filter 와 같은 조건. 키워드 후보를 벡터 필터와 맞추는 데 쓴다."""
    status = row.get("status", "")
    if statuses:
        if status not in statuses:
            return False
    elif not include_deprecated and status == "deprecated":
        return False
    if scheme and row.get("scheme", "") != scheme:
        return False
    return True


def bm25_tokens(side: dict) -> list[str]:
    """색인용 토큰. 라벨은 세 번, 대체·숨은 라벨은 두 번, 정의는 한 번 센다."""
    label = tokenize(side.get("label", ""))
    alt = tokenize(" ".join(list(side.get("alt") or []) + list(side.get("hidden") or [])))
    note = tokenize(side.get("note", ""))
    return label * 3 + alt * 2 + note


class Bm25:
    def __init__(self, docs: dict[str, list[str]], k1: float = BM25_K1, b: float = BM25_B):
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.tf = {i: Counter(t) for i, t in docs.items()}
        self.dl = {i: len(t) for i, t in docs.items()}
        self.avgdl = (sum(self.dl.values()) / self.n) if self.n else 0.0
        df: Counter = Counter()
        for c in self.tf.values():
            df.update(c.keys())
        self.idf = {t: math.log(1 + (self.n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def rank(self, query: str, ids=None, limit: int = 50) -> list[str]:
        q = set(tokenize(query))
        pool = self.tf.keys() if ids is None else [i for i in ids if i in self.tf]
        scores: dict[str, float] = {}
        for i in pool:
            tf = self.tf[i]
            s = 0.0
            for t in q:
                f = tf.get(t, 0)
                if not f or not self.avgdl:
                    continue
                norm = f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.dl[i] / self.avgdl))
                s += self.idf.get(t, 0.0) * norm
            if s > 0:
                scores[i] = s
        return [i for i, _ in sorted(scores.items(), key=lambda kv: -kv[1])][:limit]


def rrf_fuse(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for r, i in enumerate(ranking, 1):
            scores[i] += 1.0 / (k + r)
    return sorted(scores.items(), key=lambda kv: -kv[1])


def tbox_doc(row: dict):
    """TBox 한 요소 -> (벡터 입력 텍스트, zvec 필드). 라벨이 없으면 None."""
    names = list(row.get("pref_en") or []) + list(row.get("pref_ko") or [])
    if not names:
        return None
    label = " / ".join(names)
    alt = row.get("alt") or []
    note = row.get("note") or ""
    text = label + (f" ({', '.join(alt)})" if alt else "") + (": " + note if note else "")
    fields = {"iri": row["iri"], "label": label, "tkind": row.get("tkind", ""),
              "domain": " ".join(row.get("domain") or []), "range": " ".join(row.get("range") or []),
              "super": " ".join(row.get("super") or [])}
    return text, fields


def side_entry(row: dict, fields: dict) -> dict:
    """키워드 색인과 필터 재적용에 쓰는 항목. zvec 필드를 모두 포함하고, 라벨과 정의 텍스트를 더한다."""
    return dict(fields, alt=list(row.get("alt") or []), hidden=list(row.get("hidden") or []),
                note=row.get("note") or row.get("scope_note") or "")


def expand_tbox(hits: list[dict], rows_by_iri: dict, max_add: int = 10) -> list[dict]:
    """검색 hit 를 먼저 두고, 그 뒤에 TBox 이웃을 덧붙인다.

    클래스: 그 domain 을 가진 속성, 상위 클래스. 속성: domain 클래스, range 클래스, 상위 속성.
    max_add 를 넘기지 않는다. rows_by_iri 는 kb_tbox.jsonl 을 iri 로 색인한 것이다.
    """
    def view(iri: str, reason: str, extra: dict | None = None) -> dict:
        r = rows_by_iri.get(iri, {})
        d = {"iri": iri, "label": " / ".join((r.get("pref_en") or []) + (r.get("pref_ko") or [])),
             "tkind": r.get("tkind", ""), "domain": list(r.get("domain") or []),
             "range": list(r.get("range") or []), "super": list(r.get("super") or []), "reason": reason}
        if extra:
            d.update(extra)
        return d

    seen: set[str] = set()
    out: list[dict] = []
    for h in hits:
        if h["iri"] in seen:
            continue
        seen.add(h["iri"])
        out.append(view(h["iri"], "hit", {"score": h.get("score")}))

    props_of: dict[str, list[str]] = defaultdict(list)
    for iri, r in rows_by_iri.items():
        if r.get("tkind") == "property":
            for d in r.get("domain") or []:
                props_of[d].append(iri)

    added: list[dict] = []

    def add(iri: str, reason: str) -> None:
        if len(added) >= max_add or iri in seen or iri not in rows_by_iri:
            return
        seen.add(iri)
        added.append(view(iri, reason))

    for h in hits:
        r = rows_by_iri.get(h["iri"])
        if not r:
            continue
        if r.get("tkind") == "class":
            for p in props_of.get(h["iri"], []):
                add(p, "property-of-class")
            for s in r.get("super") or []:
                add(s, "superclass")
        elif r.get("tkind") == "property":
            for d in r.get("domain") or []:
                add(d, "domain-of")
            for g in r.get("range") or []:
                add(g, "range-of")
            for s in r.get("super") or []:
                add(s, "superproperty")
    return out + added
