"""skb-semantic-search 의 순수 함수 모음 (mlx·zvec·rdflib 없이 import 가능, 테스트 대상).

임베딩 모델·차원·접두어 규약은 이 파일의 상수가 단일 출처다. 바꾸면 인덱스를 전부 다시 만들어야 하고
manifest 의 model/dim 이 달라 status 가 stale 로 보고한다.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skb_layout  # noqa: E402

MODEL = "mlx-community/embeddinggemma-2-bf16"
DIM = 768
DOC_PREFIX = "title: none | text: "
QUERY_PREFIX = "task: search result | query: "
MAX_TOKENS = 512

KINDS = ("concepts", "evidence")
STORE_NAMES = {"concepts": "zvec_store_concepts_eg2", "evidence": "zvec_store_evidence_eg2"}
FIELDS = {"concepts": ("iri", "label", "status", "scheme"), "evidence": ("seed_id", "title", "uri", "md_path")}
SEMANTIC_DIR = "ontology/system/semantic"  # layout: 이 없을 때의 기본값. 실제 경로는 skb_layout.semantic_dir
SKIP_SUFFIXES = (".inferred.ttl", ".shapes.ttl")
MANIFEST = "search_manifest.json"
CONCEPTS_JSONL = "kb_concepts.jsonl"


def sql_quote(value: str) -> str:
    """zvec filter 식의 문자열 리터럴. 작은따옴표는 두 번 써서 이스케이프한다."""
    return "'" + str(value).replace("'", "''") + "'"


def concept_filter(statuses=None, include_deprecated=False, scheme=None) -> str | None:
    """개념 검색 필터. 기본은 deprecated 제외(status 가 빈 개념은 통과)."""
    parts = []
    if statuses:
        parts.append("(" + " or ".join(f"status = {sql_quote(s)}" for s in statuses) + ")")
    elif not include_deprecated:
        parts.append("status != 'deprecated'")
    if scheme:
        parts.append(f"scheme = {sql_quote(scheme)}")
    return " and ".join(parts) or None


def evidence_filter(uri=None, uri_contains=None) -> str | None:
    parts = []
    if uri:
        parts.append(f"uri = {sql_quote(uri)}")
    if uri_contains:
        parts.append("uri like " + sql_quote("%" + uri_contains + "%"))
    return " and ".join(parts) or None


def group_by_doc(hits: list[dict], k: int, key: str = "uri") -> list[dict]:
    """청크 hit 를 문서(key) 단위로 묶어 문서별 최고 점수 청크만 남기고 상위 k 문서를 돌려준다.

    hit 는 sim 이 큰 순서로 들어온다고 가정하지 않는다. 입력 순서와 무관하게 정렬한다.
    """
    best: dict[str, dict] = {}
    count: dict[str, int] = {}
    for h in hits:
        g = h.get(key) or h.get("seed_id", "")
        count[g] = count.get(g, 0) + 1
        if g not in best or h["sim"] > best[g]["sim"]:
            best[g] = h
    out = [dict(best[g], chunks_hit=count[g]) for g in best]
    out.sort(key=lambda h: -h["sim"])
    return out[:k]


def strip_frontmatter(text: str) -> str:
    """evidence md 노트의 생성 주석과 frontmatter 를 뺀 본문."""
    return re.sub(r"\A(<!--.*?-->\s*)?---\n.*?\n---\n", "", text, flags=re.S).strip()


def concept_doc(row: dict) -> tuple[str, dict] | None:
    """kb_concepts.jsonl 한 줄 -> (임베딩 텍스트, zvec 필드). prefLabel 이 없으면 None."""
    names = list(row.get("pref_en") or []) + list(row.get("pref_ko") or [])
    if not names:
        return None
    label = " / ".join(names)
    alt = row.get("alt") or []
    note = row.get("scope_note") or ""
    text = label + (f" ({', '.join(alt)})" if alt else "") + (": " + note if note else "")
    return text, {"iri": row["iri"], "label": label, "status": row.get("status", ""), "scheme": row.get("scheme", "")}


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def rel_to(target: Path, p: Path) -> str:
    try:
        return str(p.relative_to(target))
    except ValueError:
        return str(p)


def semantic_ttl_files(target: Path) -> list[Path]:
    root = skb_layout.semantic_dir(target)
    return sorted(p for p in root.rglob("*.ttl") if not p.name.endswith(SKIP_SUFFIXES)) if root.exists() else []


def source_fingerprint(target: Path, kind: str) -> str:
    """인덱스 원천의 내용 지문. 원천이 같으면 같고, 한 파일이라도 바뀌면 달라진다."""
    h = hashlib.sha256()
    if kind == "concepts":
        for p in semantic_ttl_files(target):
            h.update(rel_to(target, p).encode() + b"\0" + sha256_file(p).encode() + b"\n")
    elif kind == "evidence":
        seeds = skb_layout.seeds_path(target)
        if seeds.exists():
            h.update(sha256_file(seeds).encode())
    else:
        raise ValueError(kind)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def manifest_path(store_dir: Path) -> Path:
    return store_dir / MANIFEST


def read_manifest(store_dir: Path) -> dict:
    p = manifest_path(store_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def write_manifest_entry(store_dir: Path, kind: str, entry: dict) -> None:
    m = read_manifest(store_dir)
    m[kind] = entry
    manifest_path(store_dir).write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


def freshness(target: Path, store_dir: Path, kind: str) -> dict:
    """kind 인덱스의 신선도. state: fresh | stale | missing."""
    m = read_manifest(store_dir).get(kind)
    store = store_dir / STORE_NAMES[kind]
    if not m or not store.exists():
        return {"kind": kind, "state": "missing", "reasons": ["index or manifest not found"]}
    reasons = []
    if m.get("limited"):
        reasons.append("partial index (built with --limit)")
    if m.get("model") != MODEL:
        reasons.append(f"model changed ({m.get('model')} -> {MODEL})")
    if m.get("dim") != DIM:
        reasons.append(f"dim changed ({m.get('dim')} -> {DIM})")
    now = source_fingerprint(target, kind)
    if m.get("source_fingerprint") != now:
        reasons.append("source changed since index was built")
    return {"kind": kind, "state": "stale" if reasons else "fresh", "reasons": reasons,
            "built_at": m.get("built_at"), "indexed": m.get("indexed"), "skipped": m.get("skipped")}
