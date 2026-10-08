#!/usr/bin/env python3
"""skb-semantic-search — SKOS 개념과 evidence 청크의 의미 검색 (EmbeddingGemma 2 + zvec).

  semantic_search.py index  concepts|evidence --target KB [--limit N]
  semantic_search.py search concepts "질의" --target KB [-k 5] [--status accepted,draft] [--include-deprecated] [--scheme IRI] [--json]
  semantic_search.py search evidence "질의" --target KB [-k 5] [--uri URL | --uri-contains STR] [--group-by-doc] [--json]
  semantic_search.py status --target KB [--json]      # 종료 코드: 0 모두 fresh, 1 stale/missing 있음

인덱스는 정본이 아니라 파생물이다. 정본은 TTL(개념)과 evidence/seeds.jsonl 이고, 인덱스는 언제든 다시 만든다.
문서 소속(어느 문서의 청크인가)은 임베딩이 아니라 zvec 필드(uri)로 다룬다: --uri/--uri-contains/--group-by-doc.
실행 환경: SKB_SEARCH_PYTHON (기본 python3; mlx-vlm, transformers, zvec 필요).
개념 추출은 rdflib 가 있는 SKB_RDF_PYTHON 으로 실행한다(기본: 현재 python 이 rdflib 를 import 할 수 있어야 한다).
"""
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
    if os.environ.get("SKB_RDF_PYTHON"):
        return os.environ["SKB_RDF_PYTHON"]
    try:
        import rdflib  # noqa: F401
        return sys.executable
    except ImportError:
        sys.exit("rdflib 가 있는 python 을 찾지 못했다. SKB_RDF_PYTHON 을 지정하라.")


# ---- index
def load_rows(a, kind):
    target = Path(a.target).resolve()
    sd = store_dir(a)
    skipped = 0
    rows = []
    if kind == "concepts":
        r = subprocess.run([_rdf_python(), str(HERE / "extract_concepts.py"), "--target", str(target), "--out", str(sd / C.CONCEPTS_JSONL)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("개념 추출 실패:\n" + r.stderr[-800:])
        out(r.stdout.strip())
        for l in open(sd / C.CONCEPTS_JSONL, encoding="utf-8"):
            d = C.concept_doc(json.loads(l))
            if d is None:
                skipped += 1
            else:
                rows.append((d[0], d[1]))
    else:
        for l in open(C.skb_layout.seeds_path(target), encoding="utf-8"):
            d = json.loads(l)
            p = d.get("md_path")
            f = target / p if p else None
            body = C.strip_frontmatter(f.read_text(encoding="utf-8")) if f and f.exists() else ""
            if not body:
                skipped += 1
                continue
            rows.append((body, {"seed_id": d["id"], "title": d.get("title") or "", "uri": d.get("uri") or "", "md_path": p}))
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
    C.write_manifest_entry(sd, kind, {"model": C.MODEL, "dim": C.DIM, "built_at": C.now_iso(), "indexed": len(rows),
                                      "skipped": skipped, "limited": bool(a.limit), "source_fingerprint": fp,
                                      "seconds": round(time.time() - t0, 1)})
    out(f"✅ {kind}: {len(rows)}개 (건너뜀 {skipped}) -> {sd / C.STORE_NAMES[kind]}")


# ---- search
def cmd_search(a):
    import zvec
    sd = store_dir(a)
    col = _zvec(sd, a.kind, create=False)
    if a.kind == "concepts":
        flt = C.concept_filter([s for s in (a.status or "").split(",") if s] or None, a.include_deprecated, a.scheme)
    else:
        flt = C.evidence_filter(a.uri, a.uri_contains)
    fetch = min(max(a.k * 8, 50), 300) if getattr(a, "group_by_doc", False) else a.k
    v = embed([a.query], C.QUERY_PREFIX)[0]
    res = col.query(queries=zvec.Query("embedding", vector=v.tolist()), topk=fetch, filter=flt,
                    output_fields=list(C.FIELDS[a.kind]))
    hits = [dict({f: d.field(f) for f in C.FIELDS[a.kind]}, sim=round(1 - d.score, 4)) for d in res]
    if getattr(a, "group_by_doc", False):
        hits = C.group_by_doc(hits, a.k)
    else:
        hits = hits[:a.k]
    fm = C.read_manifest(sd).get(a.kind)
    if a.json:
        out(json.dumps({"filter": flt, "hits": hits}, ensure_ascii=False, indent=1))
        return
    if fm is None:
        print("⚠ manifest 가 없어 인덱스 신선도를 알 수 없다 (status 로 확인)", file=sys.stderr)
    for h in hits:
        extra = f"  ({h['chunks_hit']} chunks)" if "chunks_hit" in h else ""
        if a.kind == "concepts":
            out(f"  sim={h['sim']:.3f}  {h['label']}  [{h['status'] or '-'}]\n           {h['iri']}")
        else:
            out(f"  sim={h['sim']:.3f}  {h['uri']}{extra}\n           {h['md_path']}")
    if not hits:
        out("  (결과 없음)" + (f"  필터: {flt}" if flt else ""))


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
    p.add_argument("--status", help="concepts: 쉼표로 구분한 status 목록"); p.add_argument("--include-deprecated", action="store_true")
    p.add_argument("--scheme", help="concepts: skos:inScheme IRI")
    p.add_argument("--uri", help="evidence: 이 문서(uri)로 제한"); p.add_argument("--uri-contains", help="evidence: uri 에 이 문자열이 있는 문서로 제한")
    p.add_argument("--group-by-doc", action="store_true", help="evidence: 문서당 최고 청크 하나만")
    p.set_defaults(fn=cmd_search)
    p = sub.add_parser("status", parents=[common]); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_status)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
