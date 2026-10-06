#!/usr/bin/env python3
"""evidence 카탈로그 — seeds.jsonl(청크 단위 평면 행)을 정규화해 TTL 정본과 청크 JSONL 로 나눈다.

  catalog.ttl      발행자·문서·청크 프로파일(어휘 ec: = references/catalog/evidence-catalog.ttl)
  chunks.jsonl     청크 행(id, source_id, index, char_len, content_hash). TTL 은 이 파일을 ec:ChunkSet 으로 기술한다
  schema/          어휘와 SHACL 형상 사본(catalog_validate 가 같은 디렉토리에서 읽는다)

문서의 날짜·저자·발행 주체는 evidence/raw 원문 frontmatter 의 제공자 선언값을 그대로 옮긴다(추정 금지).
seed.uri 와 raw 의 source: 가 같으면 같은 문서로 잇는다. seeds.jsonl 은 지우지 않는다.
기본은 dry-run, --apply 로 쓴다. 출력은 결정적이다(같은 입력 → 같은 파일).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import shutil
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as _layout  # noqa: E402

EC_NS = "https://skb.dev/ontology/evidence-catalog#"
REF_DIR = Path(__file__).resolve().parent.parent / "references" / "catalog"

# host 접미 → (publisher_id, name, kind). 여기 없는 host 는 auto(이름 미확정)로 만들고 사람이 채운다.
KNOWN = {
    "arxiv.org": ("arxiv", "arXiv", "repository"), "ar5iv.labs.arxiv.org": ("arxiv", "arXiv", "repository"),
    "github.com": ("github", "GitHub", "platform"), "raw.githubusercontent.com": ("github", "GitHub", "platform"),
    "huggingface.co": ("huggingface", "Hugging Face", "platform"),
    "plato.stanford.edu": ("stanford-sep", "Stanford Encyclopedia of Philosophy", "encyclopedia"),
    "wikipedia.org": ("wikipedia", "Wikipedia", "encyclopedia"),
    "w3.org": ("w3c", "W3C", "standards-body"), "html.spec.whatwg.org": ("whatwg", "WHATWG", "standards-body"),
    "link.springer.com": ("springer", "Springer", "publisher"), "journals.plos.org": ("plos", "PLOS", "publisher"),
    "dl.acm.org": ("acm", "ACM Digital Library", "publisher"),
    "openai.com": ("openai", "OpenAI", "company"), "anthropic.com": ("anthropic", "Anthropic", "company"),
    "medium.com": ("medium", "Medium", "platform"), "substack.com": ("substack", "Substack", "platform"),
    "nature.com": ("nature", "Nature", "publisher"), "ieee.org": ("ieee", "IEEE", "publisher"),
    "aclanthology.org": ("acl-anthology", "ACL Anthology", "repository"),
    "openreview.net": ("openreview", "OpenReview", "repository"),
}
NONE_PROFILE = {"strategy": "none", "unit": "char", "note": "청크 길이 정보 없음"}
_PUB_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?$")


def parse_frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    return {k.strip(): v.strip() for k, _, v in (ln.partition(":") for ln in m.group(1).splitlines())}


def publisher_of(url: str) -> tuple[str, str | None, str, str]:
    host = urllib.parse.urlparse(url).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    for suf, v in KNOWN.items():
        if host == suf or host.endswith("." + suf):
            return v + (host,)
    parts = host.split(".")
    reg = ".".join(parts[-2:]) if len(parts) >= 2 else host
    return (re.sub(r"[^a-z0-9]+", "-", reg).strip("-"), None, "web", host)


def slug(text: str) -> str:
    t = text[len("evidence:seed:"):] if text.startswith("evidence:seed:") else text
    return re.sub(r"[^A-Za-z0-9._-]+", "-", t).strip("-")


def profile_id(obj: dict) -> str:
    return "cp-" + hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:8]


def index_raw(raw_dir: Path, target: Path) -> dict[str, dict]:
    """raw 원문 frontmatter 를 source URL 로 색인한다. 같은 source 가 여럿이면 경로 정렬상 첫 파일."""
    out: dict[str, dict] = {}
    if not raw_dir.is_dir():
        return out
    for p in sorted(raw_dir.glob("*.md")):
        fm = parse_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
        src = fm.get("source")
        if src and src not in out:
            fm["_path"] = _layout.rel(target, p)
            out[src] = fm
    return out


def _json_list(value: str | None) -> list:
    try:
        v = json.loads(value or "")
        return v if isinstance(v, list) else []
    except ValueError:
        return []


def authorship_state(mentions: int, resolved: int, raw_reason: str | None) -> tuple[str, str | None]:
    """저자 언급 수와 해소 수에서 상태를 계산한다(저장하지 않는 파생값의 투영). 0 → unresolved(+사유), 일부 → partial, 전부 → resolved."""
    if mentions == 0:
        return "unresolved", raw_reason or "not_extracted"
    return ("resolved", None) if resolved == mentions else ("partial", None)


def build_model(rows: list[dict], raw: dict[str, dict], std_profile: dict,
                author_info: dict[str, dict] | None = None) -> tuple[dict, dict, list, list, dict]:
    """seeds 행 → (publishers, profiles, sources, chunks, stats). 파일 쓰기 없음.
    author_info: 문서 URL → {mentions, resolved, creators}(등록·식별 그래프에서 계산). 없으면 raw 선언 저자 수를 언급 수로 보고 해소 0."""
    author_info = author_info or {}
    base_of = lambda d: re.sub(r"_\d{4}$", "", d["id"]) if re.search(r"_\d{4}$", d["id"]) else d["id"]
    bases: dict[str, set] = collections.defaultdict(set)
    for d in rows:
        bases[base_of(d)].add(d.get("uri") or d["id"])

    def src_of(d):
        b, key = base_of(d), d.get("uri") or d["id"]
        return b if len(bases[b]) == 1 else b + "-" + hashlib.sha256(key.encode()).hexdigest()[:8]

    docs: dict[str, dict] = {}
    chunks: list[dict] = []
    seen: set[str] = set()
    dup_ids = 0
    for d in rows:
        if d["id"] in seen:
            dup_ids += 1
            continue
        seen.add(d["id"])
        sid = src_of(d)
        ch = d.get("chunk") or {}
        doc = docs.setdefault(sid, {"retrieved": set(), "title": set(), "uri": set(), "total": set(), "snapshot": None, "n": 0, "has_len": False, "tool": set()})
        for k, f in (("retrieved", "retrieved_at"), ("title", "title"), ("uri", "uri"), ("tool", "tool_version")):
            if d.get(f) is not None:
                doc[k].add(d[f])
        if ch.get("total") is not None:
            doc["total"].add(ch["total"])
        if d.get("snapshot") and not doc["snapshot"]:
            doc["snapshot"] = d["snapshot"]
        doc["n"] += 1
        row = {"id": d["id"], "source_id": sid, "index": ch.get("index"), "content_hash": d.get("content_hash")}
        if "char_end" in ch:
            row["char_len"] = ch["char_end"] - ch.get("char_start", 0)
            doc["has_len"] = True
        chunks.append(row)

    pubs: dict[str, dict] = {}
    profiles: dict[str, dict] = {}
    sources = []
    n_raw = 0
    for sid, doc in sorted(docs.items()):
        uri = sorted(doc["uri"])[0] if doc["uri"] else ""
        is_web = uri.startswith("http")
        if is_web:
            p_id, name, kind, host = publisher_of(uri)
            p = pubs.setdefault(p_id, {"publisher_id": p_id, "name": name, "kind": kind, "hosts": [], "curation": "known" if name else "auto"})
            if host not in p["hosts"]:
                p["hosts"].append(host)
        else:
            p_id = "local"
            pubs.setdefault("local", {"publisher_id": "local", "name": "저장소 내부·로컬 문서", "kind": "internal", "hosts": [], "curation": "known"})
        prof = dict(std_profile if doc["has_len"] else NONE_PROFILE)
        if doc["has_len"] and doc["tool"]:
            prof["producer"] = sorted(doc["tool"])[0]
        pid_ = profile_id(prof)
        profiles.setdefault(pid_, {"chunk_profile_id": pid_, **prof})
        row = {"source_id": sid, "source_url": uri if is_web else None,
               "title": sorted(doc["title"])[0] if doc["title"] else None,
               "publisher_id": p_id, "source_type": "web" if is_web else "internal",
               "retrieved_at": sorted(doc["retrieved"])[0] if doc["retrieved"] else None,
               "chunk_profile_id": pid_, "chunk_count": doc["n"],
               "chunk_total_declared": sorted(doc["total"])[0] if len(doc["total"]) == 1 else None,
               "snapshot": doc["snapshot"], "authors": [], "authorship": ("unresolved", "not_extracted"),
               "author_mentions": 0, "author_resolved": 0, "creators": []}
        if not is_web and uri:
            row["legacy_uri"] = uri
        fm = raw.get(uri) if is_web else None
        if fm:
            n_raw += 1
            row["raw_path"] = fm["_path"]
            if fm.get("collected_at"):
                row["retrieved_at"] = fm["collected_at"]
                row["collected_at_basis"] = fm.get("collected_at_basis")
            pub = fm.get("published_at", "")
            if _PUB_DATE.match(pub):
                row["published_at"] = pub
            row["published_at_source"] = fm.get("published_at_source") or "none:not-recorded"
            for k in ("publisher", "publisher_source", "publisher_type", "document_type"):
                if fm.get(k):
                    row["declared_" + k if k == "publisher" else k] = fm[k]
            authors = [a["name"] for a in _json_list(fm.get("authors")) if isinstance(a, dict) and a.get("name")]
            row["authors"] = authors
            info = author_info.get(uri)
            mentions = info["mentions"] if info else len(authors)
            resolved = info["resolved"] if info else 0
            row["author_mentions"], row["author_resolved"] = mentions, resolved
            row["creators"] = info["creators"] if info else []
            row["authorship"] = authorship_state(mentions, resolved, fm.get("authors_source"))
            accounts = _json_list(fm.get("accounts"))
            if accounts:
                row["accounts"] = accounts
        sources.append(row)
    stats = {"sources": len(sources), "chunks": len(chunks), "publishers": len(pubs), "profiles": len(profiles),
             "raw_linked_sources": n_raw, "duplicate_seed_ids_skipped": dup_ids,
             "resolved_sources": sum(1 for s in sources if s["authorship"][0] == "resolved")}
    return pubs, profiles, sources, chunks, stats


def write_ttl(path: Path, pubs: dict, profiles: dict, sources: list, chunk_file: Path, n_chunks: int, base: str) -> None:
    from rdflib import Graph, Literal, Namespace, RDF, URIRef
    from rdflib.namespace import DCAT, DCTERMS, SKOS, XSD
    EC = Namespace(EC_NS)
    PROV = Namespace("http://www.w3.org/ns/prov#")
    B = Namespace(base)
    g = Graph()
    for pfx, ns in (("ec", EC), ("dcat", DCAT), ("dcterms", DCTERMS), ("skos", SKOS), ("xsd", XSD), ("prov", PROV), ("cat", B)):
        g.bind(pfx, ns)
    for p in pubs.values():
        u = B["publisher/" + p["publisher_id"]]
        g.add((u, RDF.type, EC.Publisher))
        if p.get("name"):
            g.add((u, SKOS.prefLabel, Literal(p["name"], lang="ko" if re.search("[가-힣]", p["name"]) else "en")))
        g.add((u, EC.publisherKind, Literal(p["kind"])))
        g.add((u, EC.curation, Literal(p["curation"])))
        for h in p["hosts"]:
            g.add((u, EC.hostName, Literal(h)))
    for pr in profiles.values():
        u = B["profile/" + pr["chunk_profile_id"]]
        g.add((u, RDF.type, EC.ChunkProfile))
        for k, pred, dt in (("strategy", EC.strategy, None), ("unit", EC.unit, None), ("size", EC.size, XSD.integer), ("overlap", EC.overlap, XSD.integer),
                            ("min_chunk", EC.minChunk, XSD.integer), ("overlap_mode", EC.overlapMode, None),
                            ("producer", EC.producer, None), ("note", EC.profileNote, None)):
            if pr.get(k) is not None:
                g.add((u, pred, Literal(pr[k], datatype=dt) if dt else Literal(pr[k])))
    for s_ in sources:
        u = B["source/" + slug(s_["source_id"])]
        g.add((u, RDF.type, EC.Source))
        g.add((u, EC.legacySeedPrefix, Literal(s_["source_id"])))
        if s_.get("title") is not None:
            g.add((u, DCTERMS.title, Literal(s_["title"])))
        if s_.get("source_url"):
            g.add((u, DCTERMS.source, Literal(s_["source_url"], datatype=XSD.anyURI)))
        g.add((u, DCTERMS.publisher, B["publisher/" + s_["publisher_id"]]))
        g.add((u, EC.sourceType, Literal(s_["source_type"])))
        if s_.get("retrieved_at"):
            g.add((u, PROV.generatedAtTime, Literal(s_["retrieved_at"], datatype=XSD.dateTime)))
        g.add((u, EC.chunkProfile, B["profile/" + s_["chunk_profile_id"]]))
        g.add((u, EC.chunkCount, Literal(s_["chunk_count"], datatype=XSD.integer)))
        if s_.get("chunk_total_declared") is not None:
            g.add((u, EC.chunkTotalDeclared, Literal(s_["chunk_total_declared"], datatype=XSD.integer)))
        for au in s_["authors"]:
            g.add((u, EC.authorRaw, Literal(au)))
        state, reason = s_["authorship"]
        g.add((u, EC.authorMentionCount, Literal(s_["author_mentions"], datatype=XSD.integer)))
        g.add((u, EC.authorResolvedCount, Literal(s_["author_resolved"], datatype=XSD.integer)))
        for c in s_["creators"]:
            g.add((u, DCTERMS.creator, URIRef(c)))
        g.add((u, EC.authorshipState, Literal(state)))
        if reason:
            g.add((u, EC.authorshipReason, Literal(reason)))
        if s_.get("legacy_uri"):
            g.add((u, EC.legacyUri, Literal(s_["legacy_uri"])))
        if s_.get("snapshot"):
            g.add((u, EC.snapshotJson, Literal(json.dumps(s_["snapshot"], ensure_ascii=False, sort_keys=True))))
        if s_.get("raw_path"):
            g.add((u, EC.rawPath, Literal(s_["raw_path"])))
            if s_.get("collected_at_basis"):
                g.add((u, EC.collectedAtBasis, Literal(s_["collected_at_basis"])))
            if s_.get("published_at"):
                dt = XSD.dateTime if "T" in s_["published_at"] else XSD.date
                g.add((u, DCTERMS.issued, Literal(s_["published_at"], datatype=dt)))
            g.add((u, EC.publishedAtSource, Literal(s_["published_at_source"])))
            for k, pred in (("declared_publisher", EC.declaredPublisher), ("publisher_source", EC.publisherSource),
                            ("publisher_type", EC.publisherType), ("document_type", EC.documentType)):
                if s_.get(k):
                    g.add((u, pred, Literal(s_[k])))
            if s_.get("accounts"):
                g.add((u, EC.accountJson, Literal(json.dumps(s_["accounts"], ensure_ascii=False, sort_keys=True))))
    d = B["chunkset/chunks"]
    g.add((d, RDF.type, EC.ChunkSet))
    g.add((d, DCAT.downloadURL, Literal(chunk_file.name, datatype=XSD.anyURI)))
    g.add((d, EC.rowCount, Literal(n_chunks, datatype=XSD.integer)))
    g.add((d, EC.sha256, Literal(hashlib.sha256(chunk_file.read_bytes()).hexdigest())))
    g.add((d, EC.rowSchema, Literal("id, source_id, index, char_len, content_hash")))
    path.write_text(g.serialize(format="turtle"), encoding="utf-8")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="catalog")
    ap.add_argument("--target", default=".", help="KB root")
    ap.add_argument("--base", default="https://example.org/skb/evidence-catalog/", help="인스턴스 IRI 접두")
    ap.add_argument("--chunk-size", type=int, default=1200, help="chunker 설정(seed 에 기록되지 않아 인자로 선언)")
    ap.add_argument("--chunk-overlap", type=int, default=100)
    ap.add_argument("--apply", action="store_true", help="파일을 쓴다(기본은 dry-run)")
    a = ap.parse_args(argv)
    target = Path(a.target).resolve()
    lay = _layout.resolve_layout(target)
    if not lay["seeds_path"].exists():
        print("ERROR: seeds.jsonl 이 없다", file=sys.stderr)
        return 1
    rows = [json.loads(line) for line in lay["seeds_path"].open(encoding="utf-8") if line.strip()]
    std = {"strategy": "paragraph-sentence-merge", "unit": "char", "size": a.chunk_size, "overlap": a.chunk_overlap,
           "min_chunk": 300, "overlap_mode": "forward-prefix",
           "note": "size/overlap 은 builder 인자로 선언한 값이다(seed 에 기록되지 않음)"}
    import identity_lib as _il
    author_info = _il.doc_author_info(_il.load_dir_graph(lay["registrations_dir"]), _il.load_file_graph(lay["identity_dir"] / "identifications.ttl"))
    pubs, profiles, sources, chunks, stats = build_model(rows, index_raw(lay["raw_dir"], target), std, author_info)
    print(json.dumps(stats, ensure_ascii=False))
    if not a.apply:
        print("dry-run: 파일을 쓰지 않았다. --apply 로 쓴다.")
        return 0
    out = lay["catalog_dir"]
    (out / "schema").mkdir(parents=True, exist_ok=True)
    for n in ("evidence-catalog.ttl", "evidence-catalog.shapes.ttl"):
        shutil.copy(REF_DIR / n, out / "schema" / n)
    with open(out / "chunks.jsonl", "w", encoding="utf-8") as f:
        for r in chunks:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_ttl(out / "catalog.ttl", pubs, profiles, sources, out / "chunks.jsonl", len(chunks), a.base)
    print(f"written: {_layout.rel(target, out)}/catalog.ttl, chunks.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
