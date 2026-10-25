#!/usr/bin/env python3
"""skb-semantic-search — SKOS 개념과 evidence 청크의 의미 검색 (EmbeddingGemma 2 + zvec).

  semantic_search.py index  concepts|evidence --target KB [--limit N]
  semantic_search.py search concepts "질의" --target KB [-k 5] [--status accepted,draft] [--include-deprecated] [--scheme IRI] [--json]
  semantic_search.py search evidence "질의" --target KB [-k 5] [--uri URL | --uri-contains STR] [--group-by-doc] [--json]
  semantic_search.py status --target KB [--json]      # 종료 코드: 0 모두 fresh, 1 stale/missing 있음
  semantic_search.py index tbox --target KB           # TBox(class·property) 색인 (hybrid)
  semantic_search.py expand "질의" --target KB [--max-add 10] [--json]   # TBox 검색 후 domain·range·상하위 확장
  semantic_search.py sparql-search "질문"              # 자주 묻는 SPARQL 템플릿 찾기 (IRI 없이)
  semantic_search.py sparql-run --template ID --bind CLASS=q:텍스트 --target KB [--dry-run]

인덱스는 정본이 아니라 파생물이다. 정본은 TTL(개념)과 evidence/seeds.jsonl 이고, 인덱스는 언제든 다시 만든다.
문서 소속(어느 문서의 청크인가)은 임베딩이 아니라 zvec 필드(uri)로 다룬다: --uri/--uri-contains/--group-by-doc.
실행 환경: SKB_SEARCH_PYTHON (기본 python3; mlx-vlm, transformers, zvec 필요).
개념 추출은 rdflib 가 있는 SKB_RDF_PYTHON 으로 실행한다(기본: 현재 python 이 rdflib 를 import 할 수 있어야 한다).
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ss_common as C
import ss_hybrid as H

HERE = Path(__file__).resolve().parent

# zvec 네이티브 라이브러리가 stdout 에 로그 줄을 직접 찍어 --json 출력을 깨뜨린다.
# fd 1 을 stderr 로 돌리고, 결과는 원래 stdout 의 복제본(_OUT)으로만 내보낸다.
_OUT = os.fdopen(os.dup(1), "w", encoding="utf-8")
os.dup2(2, 1)


def out(*args, **kw):
    kw.setdefault("file", _OUT)
    kw.setdefault("flush", True)
    print(*args, **kw)


def store_dir(a) -> Path:
    return Path(a.store_dir) if a.store_dir else Path(a.target).resolve() / "embedding"


# ---- 임베딩 (mlx 는 필요할 때만 import)
_M = {}


def _model():
    if not _M:
        from mlx_vlm.embedding_loader import load_embedding_model
        from mlx_vlm.utils import get_model_path
        from transformers import AutoTokenizer
        p = get_model_path(C.MODEL)
        _M["m"], _M["t"] = load_embedding_model(p), AutoTokenizer.from_pretrained(p)
    return _M["m"], _M["t"]


def embed(texts, prefix, bs=16):
    """길이순으로 정렬해 패딩을 줄이고 원래 순서로 되돌린다. 벡터는 모델이 L2 정규화해서 돌려준다."""
    import mlx.core as mx
    import numpy as np
    m, t = _model()
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
    out = [None] * len(texts)
    for s in range(0, len(order), bs):
        idx = order[s:s + bs]
        enc = t([prefix + texts[i] for i in idx], padding=True, truncation=True, max_length=C.MAX_TOKENS, return_tensors="np")
        e = m(**{k: mx.array(v) for k, v in enc.items()}).text_embeds
        mx.eval(e)
        for i, v in zip(idx, np.array(e.astype(mx.float32))):
            out[i] = v
    return out


def _zvec(sd: Path, kind: str, create: bool):
    import zvec
    zvec.init(log_type=zvec.LogType.FILE, log_level=zvec.LogLevel.WARN, log_dir=str(sd / "logs"))
    path = sd / C.STORE_NAMES[kind]
    if not create:
        if not path.exists():
            sys.exit(f"인덱스가 없다: {path}  (먼저 index {kind} 를 실행)")
        return zvec.open(str(path))
    if path.exists():
        shutil.rmtree(path)
    schema = zvec.CollectionSchema(
        name=f"skb_{kind}", fields=[zvec.FieldSchema(f, zvec.DataType.STRING) for f in C.FIELDS[kind]],
        vectors=zvec.VectorSchema("embedding", data_type=zvec.DataType.VECTOR_FP32, dimension=C.DIM,
                                  index_param=zvec.HnswIndexParam(metric_type=zvec.MetricType.COSINE)))
    return zvec.create_and_open(str(path), schema)


def _rdf_python() -> str:
    """rdflib 이 있는 인터프리터. SKB_RDF_PYTHON 이 우선이고, 없으면 현재 인터프리터와 python3 를 확인한다."""
    if os.environ.get("SKB_RDF_PYTHON"):
        return os.environ["SKB_RDF_PYTHON"]
    for cand in (sys.executable, "python3"):
        if subprocess.run([cand, "-c", "import rdflib"], capture_output=True).returncode == 0:
            return cand
    sys.exit("rdflib 가 있는 python 을 찾지 못했다. SKB_RDF_PYTHON 을 지정하라.")


# ---- index
def _extract(target: Path, sd: Path) -> None:
    r = subprocess.run([_rdf_python(), str(HERE / "extract_concepts.py"), "--target", str(target),
                        "--out", str(sd / C.CONCEPTS_JSONL), "--tbox-out", str(sd / C.TBOX_JSONL)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("개념 추출 실패:\n" + r.stderr[-800:])
    out(r.stdout.strip())


def load_rows(a, kind):
    """(벡터 입력 텍스트, zvec 필드, 키워드 색인 항목 또는 None) 목록과 건너뛴 수."""
    target = Path(a.target).resolve()
    sd = store_dir(a)
    rows, skipped = [], 0
    if kind == "evidence":
        for l in open(C.skb_layout.seeds_path(target), encoding="utf-8"):
            d = json.loads(l)
            p = d.get("md_path")
            f = target / p if p else None
            body = C.strip_frontmatter(f.read_text(encoding="utf-8")) if f and f.exists() else ""
            if not body:
                skipped += 1
                continue
            rows.append((body, {"seed_id": d["id"], "title": d.get("title") or "", "uri": d.get("uri") or "",
                                "md_path": p}, None))
        return rows, skipped
    _extract(target, sd)
    src, to_doc = (sd / C.CONCEPTS_JSONL, C.concept_doc) if kind == "concepts" else (sd / C.TBOX_JSONL, H.tbox_doc)
    for l in open(src, encoding="utf-8"):
        r = json.loads(l)
        d = to_doc(r)
        if d is None:
            skipped += 1
            continue
        rows.append((d[0], d[1], H.side_entry(r, d[1])))
    return rows, skipped


def cmd_index(a):
    kind = a.kind
    target = Path(a.target).resolve()
    sd = store_dir(a)
    sd.mkdir(parents=True, exist_ok=True)
    fp = C.source_fingerprint(target, kind)  # 적재 전에 계산: 도중에 원천이 바뀌면 status 가 stale 로 잡는다
    rows, skipped = load_rows(a, kind)
    if a.limit:
        rows = rows[:a.limit]
    import zvec
    t0 = time.time()
    col = _zvec(sd, kind, create=True)
    CH = 1000
    for s in range(0, len(rows), CH):
        part = rows[s:s + CH]
        vecs = embed([r[0] for r in part], C.DOC_PREFIX)
        # zvec doc id 는 : / # 같은 문자를 받지 않아 순번을 쓰고 원래 식별자는 필드에 둔다
        col.insert([zvec.Doc(id=f"{kind[0]}{s + j:06d}", vectors={"embedding": v.tolist()}, fields=r[1])
                    for j, (r, v) in enumerate(zip(part, vecs))])
        out(f"  {min(s + CH, len(rows))}/{len(rows)}  {time.time() - t0:.0f}s", flush=True)
    if kind in C.HYBRID_KINDS:  # 키워드 색인: 같은 id 로 텍스트 항목을 함께 저장한다
        with open(H.texts_path(sd, kind), "w", encoding="utf-8") as fh:
            for j, r in enumerate(rows):
                fh.write(json.dumps(dict(r[2], id=f"{kind[0]}{j:06d}"), ensure_ascii=False) + "\n")
    C.write_manifest_entry(sd, kind, {"model": C.MODEL, "dim": C.DIM, "built_at": C.now_iso(), "indexed": len(rows),
                                      "skipped": skipped, "limited": bool(a.limit), "source_fingerprint": fp,
                                      "seconds": round(time.time() - t0, 1)})
    out(f"✅ {kind}: {len(rows)}개 (건너뜀 {skipped}) -> {sd / C.STORE_NAMES[kind]}")


# ---- search
def _search_filter(a):
    if a.kind == "concepts":
        return C.concept_filter([s for s in (a.status or "").split(",") if s] or None, a.include_deprecated, a.scheme)
    if a.kind == "evidence":
        return C.evidence_filter(a.uri, a.uri_contains)
    return None  # tbox: 필터 없음


def _mode(kind, requested):
    if requested is None:
        return "hybrid" if kind in C.HYBRID_KINDS else "vector"
    if requested == "hybrid" and kind not in C.HYBRID_KINDS:
        sys.exit(f"{kind} 는 하이브리드 검색을 지원하지 않는다 (vector 만 쓴다)")
    return requested


def _vector_hits(col, kind, query, flt, fetch):
    import zvec
    v = embed([query], C.QUERY_PREFIX)[0]
    res = col.query(queries=zvec.Query("embedding", vector=v.tolist()), topk=fetch, filter=flt,
                    output_fields=list(C.FIELDS[kind]))
    return [(d.id, dict({f: d.field(f) for f in C.FIELDS[kind]}, sim=round(1 - d.score, 4))) for d in res]


def _load_sidecar(sd, kind):
    p = H.texts_path(sd, kind)
    if not p.exists():
        return None
    return {d["id"]: d for d in (json.loads(l) for l in open(p, encoding="utf-8"))}


def _run_search(a, sd, col, flt, fetch, mode):
    """mode: vector | hybrid | keyword. hybrid 는 벡터 순위와 키워드 순위를 상호 순위 결합으로 합친다.
    키워드 색인이 없으면 hybrid 는 벡터만, keyword 는 오류로 끝낸다."""
    side = _load_sidecar(sd, a.kind) if mode != "vector" else None
    vec = _vector_hits(col, a.kind, a.query, flt, fetch) if mode in ("vector", "hybrid") else []
    if mode == "vector":
        return [h for _, h in vec], "vector"
    if side is None:
        if mode == "keyword":
            sys.exit("키워드 색인이 없다 (index 를 다시 실행)")
        print("⚠ 키워드 색인이 없어 벡터 검색만 쓴다 (index 를 다시 실행)", file=sys.stderr)
        return [h for _, h in vec], "vector"
    ids = None
    if a.kind == "concepts":
        statuses = [s for s in (a.status or "").split(",") if s] or None
        ids = [i for i, e in side.items() if H.concept_match(e, statuses, a.include_deprecated, a.scheme)]
    bm = H.Bm25({i: H.bm25_tokens(e) for i, e in side.items()})
    kw = bm.rank(a.query, ids=ids, limit=fetch)
    ex = H.exact_ids(a.query, side, ids)
    w = H.HYBRID_WEIGHTS
    if mode == "keyword":
        fused = H.rrf_fuse([ex, kw], weights=[w["exact"], w["keyword"]])[:fetch]
    else:
        fused = H.rrf_fuse([ex, [i for i, _ in vec], kw], weights=[w["exact"], w["vector"], w["keyword"]])[:fetch]
    vmap = dict(vec)
    hits = []
    for i, sc in fused:
        h = {f: side[i].get(f, "") for f in C.FIELDS[a.kind]}
        h["sim"] = vmap[i]["sim"] if i in vmap else None
        h["rrf"] = round(sc, 5)
        hits.append(h)
    return hits, mode


def _score(h):
    return f"sim={h['sim']:.3f}" if h.get("sim") is not None else f"rrf={h['rrf']:.4f}"


def _hit_line(kind, h):
    if kind == "concepts":
        return f"{h['label']}  [{h['status'] or '-'}]\n           {h['iri']}"
    if kind == "tbox":
        return f"{h['label']}  [{h['tkind'] or '-'}]  domain={h['domain'] or '-'} range={h['range'] or '-'}\n           {h['iri']}"
    extra = f"  ({h['chunks_hit']} chunks)" if "chunks_hit" in h else ""
    return f"{h['uri']}{extra}\n           {h['md_path']}"


def cmd_search(a):
    sd = store_dir(a)
    col = _zvec(sd, a.kind, create=False)
    flt = _search_filter(a)
    mode = _mode(a.kind, getattr(a, "mode", None))
    grouped = getattr(a, "group_by_doc", False)
    fetch = min(max(a.k * 8, 50), 300) if (grouped or mode == "hybrid") else a.k
    hits, used = _run_search(a, sd, col, flt, fetch, mode)
    hits = C.group_by_doc(hits, a.k) if grouped else hits[:a.k]
    if a.json:
        out(json.dumps({"filter": flt, "mode": used, "hits": hits}, ensure_ascii=False, indent=1))
        return
    if C.read_manifest(sd).get(a.kind) is None:
        print("⚠ manifest 가 없어 인덱스 신선도를 알 수 없다 (status 로 확인)", file=sys.stderr)
    for h in hits:
        out(f"  {_score(h)}  {_hit_line(a.kind, h)}")
    if not hits:
        out("  (결과 없음)" + (f"  필터: {flt}" if flt else ""))


def cmd_expand(a):
    """하이브리드로 TBox 를 찾고, domain·range·상하위 관계를 따라 스키마 요소를 덧붙인다."""
    sd = store_dir(a)
    tbox_path = sd / C.TBOX_JSONL
    if not tbox_path.exists():
        sys.exit(f"TBox 추출 파일이 없다: {tbox_path} (index tbox 를 먼저 실행)")
    col = _zvec(sd, "tbox", create=False)
    ns = argparse.Namespace(kind="tbox", query=a.query, status=None, include_deprecated=False, scheme=None)
    fetch = min(max(a.k * 8, 50), 300)
    hits, used = _run_search(ns, sd, col, None, fetch, _mode("tbox", a.mode))
    rows = {r["iri"]: r for r in (json.loads(l) for l in open(tbox_path, encoding="utf-8"))}
    items = H.expand_tbox(hits[:a.k], rows, a.max_add)
    if a.json:
        out(json.dumps({"mode": used, "items": items}, ensure_ascii=False, indent=1))
        return
    for e in items:
        out(f"  [{e['reason']}] {e['label'] or '-'}  [{e['tkind'] or '-'}]\n           {e['iri']}")
    if not items:
        out("  (결과 없음)")


# ---- SPARQL 템플릿
def _resolve_q(a, text, kind, tbox_rows):
    """q:텍스트 를 IRI 로. 색인이 있으면 하이브리드(벡터+키워드), 없으면 키워드(정확 일치 우선)."""
    import ss_sparql as S
    sd = store_dir(a)
    if (sd / C.TBOX_JSONL).exists() and H.texts_path(sd, "tbox").exists() and (sd / C.STORE_NAMES["tbox"]).exists():
        try:
            col = _zvec(sd, "tbox", create=False)
            ns = argparse.Namespace(kind="tbox", query=text, status=None, include_deprecated=False, scheme=None)
            hits, used = _run_search(ns, sd, col, None, 50, "hybrid")
            cands = [h["iri"] for h in hits if h.get("tkind") == kind]
            if cands:
                return cands[0], cands[:5], used
        except SystemExit as e:  # 벡터 쪽을 쓸 수 없으면 키워드로 내려간다
            print(f"⚠ 하이브리드 해석 불가, 키워드로 대체: {e}", file=sys.stderr)
    try:
        iri, cands = S.resolve_tbox(text, tbox_rows, kind)
    except ValueError as e:
        sys.exit(str(e))
    return iri, cands, "keyword"


def cmd_eval(a):
    """정답 세트(query -> iri)로 TBox 해석 재현율을 잰다. 모드별 top1·top3·top10·MRR."""
    sd = store_dir(a)
    gold = [json.loads(l) for l in open(a.gold, encoding="utf-8")]
    col = _zvec(sd, "tbox", create=False) if any(m != "keyword" for m in a.modes) else None
    fetch = min(max(a.k, 10) * 8, 300)
    for mode in a.modes:
        ranks = []
        for g in gold:
            ns = argparse.Namespace(kind="tbox", query=g["query"], status=None, include_deprecated=False, scheme=None)
            hits, _ = _run_search(ns, sd, col, None, fetch, mode)
            ids = [h["iri"] for h in hits]
            ranks.append(ids.index(g["iri"]) + 1 if g["iri"] in ids else None)
        n = len(ranks)
        top = lambda k: sum(1 for r in ranks if r and r <= k) / n
        mrr = sum((1 / r) if r else 0.0 for r in ranks) / n
        out(f"  {mode:8s} n={n} top1={top(1):.3f} top3={top(3):.3f} top10={top(10):.3f} mrr={mrr:.3f}")


def cmd_sparql_search(a):
    import ss_sparql as S
    tpls = S.load_templates()
    errs = [e for t in tpls for e in S.validate_template(t)]
    if errs:
        sys.exit("템플릿 검증 실패:\n  " + "\n  ".join(errs))
    found = S.search_templates(a.query, tpls, a.k)
    if a.json:
        out(json.dumps(found, ensure_ascii=False, indent=1))
        return
    if not found:
        out("  (맞는 템플릿 없음)")
    for t in found:
        out(f"  {t['id']}  {t['description']}\n           slots: {t['slots']}")


def cmd_sparql_run(a):
    import ss_sparql as S
    target = Path(a.target).resolve()
    tpls = {t["id"]: t for t in S.load_templates()}
    if a.template not in tpls:
        sys.exit(f"템플릿이 없다: {a.template} (sparql-search 로 찾는다)")
    t = tpls[a.template]
    bindings = {}
    for b in a.bind or []:
        if "=" not in b:
            sys.exit(f"--bind 형식은 SLOT=값 이다: {b}")
        k, v = b.split("=", 1)
        bindings[k.strip()] = v.strip()
    tbox_rows = []
    if any(v.startswith("q:") for v in bindings.values()):
        sd = store_dir(a)
        if not (sd / C.TBOX_JSONL).exists():
            _extract(target, sd)
        tbox_rows = [json.loads(l) for l in open(sd / C.TBOX_JSONL, encoding="utf-8")]
    chosen = {}
    for slot in S.slots_of(t):
        if slot not in bindings:
            sys.exit(f"슬롯 {slot} 이 비었다. --bind {slot}=<IRI 또는 q:텍스트>")
        value, kind = bindings[slot], t["slots"][slot]
        if value.startswith("q:"):
            if kind == "instance":
                sys.exit(f"{slot} 는 개체라서 q: 검색을 쓸 수 없다. IRI 를 직접 넣어라")
            iri, cands, used = _resolve_q(a, value[2:], kind, tbox_rows)
            chosen[slot] = {"iri": iri, "candidates": cands, "mode": used}
        else:
            chosen[slot] = {"iri": value, "candidates": [], "mode": "iri"}
    try:
        query = S.fill(t, {s: chosen[s]["iri"] for s in chosen})
        S.assert_read_only(query)
    except ValueError as e:
        sys.exit(str(e))
    if a.dry_run:
        out(query)
        return
    r = subprocess.run([_rdf_python(), str(HERE / "sparql_run.py")],
                       input=json.dumps({"target": str(target), "query": query}), capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("SPARQL 실행 실패:\n" + r.stderr[-800:])
    res = json.loads(r.stdout)
    for f in res.pop("failed"):
        print("SKIP", f, file=sys.stderr)
    payload = {"template": t["id"], "bindings": chosen, "sparql": query, "vars": res["vars"], "rows": res["rows"]}
    if a.json:
        out(json.dumps(payload, ensure_ascii=False, indent=1))
        return
    for slot, c in chosen.items():
        extra = f"  (후보: {', '.join(c['candidates'])})" if c["candidates"] else ""
        out(f"  {slot} → {c['iri']}{extra}")
    out("  " + " | ".join(res["vars"]))
    for row in res["rows"]:
        out("  " + " | ".join(x or "" for x in row))
    if not res["rows"]:
        out("  (결과 없음)")


# ---- status
def cmd_status(a):
    target, sd = Path(a.target).resolve(), store_dir(a)
    rep = [C.freshness(target, sd, k) for k in C.KINDS]
    if a.json:
        out(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        for r in rep:
            line = f"{r['kind']:9s} {r['state']:8s}"
            if r["state"] != "missing":
                line += f" built={r['built_at']} indexed={r['indexed']} skipped={r['skipped']}"
            out(line + ("   ← " + "; ".join(r["reasons"]) if r["reasons"] else ""))
        if any(r["state"] != "fresh" for r in rep):
            out("재색인: semantic_search.py index <kind> --target <KB>")
    sys.exit(0 if all(r["state"] == "fresh" for r in rep) else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--target", required=True, help="KB 루트")
    common.add_argument("--store-dir", help="인덱스 디렉토리 (기본 <target>/embedding)")
    p = sub.add_parser("index", parents=[common]); p.add_argument("kind", choices=C.KINDS); p.add_argument("--limit", type=int); p.set_defaults(fn=cmd_index)
    p = sub.add_parser("search", parents=[common]); p.add_argument("kind", choices=C.KINDS); p.add_argument("query")
    p.add_argument("-k", type=int, default=5); p.add_argument("--json", action="store_true")
    p.add_argument("--mode", choices=["vector", "hybrid", "keyword"], default=None, help="기본: concepts·tbox 는 hybrid, evidence 는 vector")
    p.add_argument("--status", help="concepts: 쉼표로 구분한 status 목록"); p.add_argument("--include-deprecated", action="store_true")
    p.add_argument("--scheme", help="concepts: skos:inScheme IRI")
    p.add_argument("--uri", help="evidence: 이 문서(uri)로 제한"); p.add_argument("--uri-contains", help="evidence: uri 에 이 문자열이 있는 문서로 제한")
    p.add_argument("--group-by-doc", action="store_true", help="evidence: 문서당 최고 청크 하나만")
    p.set_defaults(fn=cmd_search)
    p = sub.add_parser("expand", parents=[common]); p.add_argument("query")
    p.add_argument("-k", type=int, default=5); p.add_argument("--max-add", type=int, default=10)
    p.add_argument("--mode", choices=["vector", "hybrid", "keyword"], default=None); p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_expand)
    p = sub.add_parser("eval", parents=[common]); p.add_argument("--gold", required=True, help="JSONL: {query, iri}")
    p.add_argument("--modes", nargs="+", default=["keyword", "vector", "hybrid"], choices=["keyword", "vector", "hybrid"])
    p.add_argument("-k", type=int, default=10); p.set_defaults(fn=cmd_eval)
    p = sub.add_parser("status", parents=[common]); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("sparql-search"); p.add_argument("query"); p.add_argument("-k", type=int, default=3)
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_sparql_search)
    p = sub.add_parser("sparql-run", parents=[common]); p.add_argument("--template", required=True)
    p.add_argument("--bind", action="append", help="SLOT=IRI 또는 SLOT=q:텍스트 (여러 번 쓴다)")
    p.add_argument("--dry-run", action="store_true", help="쿼리만 출력하고 실행하지 않는다")
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_sparql_run)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
