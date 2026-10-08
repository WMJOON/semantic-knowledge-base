#!/usr/bin/env python3
"""evidence 카탈로그 검증: ① SHACL(어휘·형상) ② TTL ↔ chunks.jsonl 정합(행 수, 해시, 문서별 청크 수, 참조 무결성)
③ rawPath 가 가리키는 원문 파일 존재(--target 이 있을 때). 종료 코드 0 = 통과.
요구: rdflib, pyshacl (skb-ontology/requirements.txt)."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as _layout  # noqa: E402


def _authorship_recompute_errors(data, target: Path) -> list[str]:
    """저장된 저자 해소 수·해소된 저자(dcterms:creator)가 등록·식별 그래프에서 다시 계산한 값과 같은지 확인한다."""
    import identity_lib as il
    from rdflib import Namespace
    from rdflib.namespace import DCTERMS, RDF
    EC = Namespace("https://skb.dev/ontology/evidence-catalog#")
    lay = _layout.resolve_layout(target)
    info = il.doc_author_info(il.load_dir_graph(lay["registrations_dir"]), il.load_file_graph(lay["identity_dir"] / "identifications.ttl"))
    out: list[str] = []
    for s in data.subjects(RDF.type, EC.Source):
        url = next((str(u) for u in data.objects(s, DCTERMS.source)), None)
        if url is None or url not in info:
            continue  # 등록이 없는 문서는 raw 선언 저자 수를 쓴다(빌더와 같은 규칙)
        got = (int(next(data.objects(s, EC.authorMentionCount))), int(next(data.objects(s, EC.authorResolvedCount))))
        want = (info[url]["mentions"], info[url]["resolved"])
        if got != want:
            out.append(f"저자 해소 수 불일치 {url}: 카탈로그 {got} / 재계산 {want} (등록·식별을 바꾼 뒤 catalog 를 다시 만들지 않았다)")
        if sorted(str(c) for c in data.objects(s, DCTERMS.creator)) != info[url]["creators"]:
            out.append(f"dcterms:creator 가 accepted 식별과 다르다 {url}")
    return out


def validate_dir(d: Path, target: Path | None = None) -> tuple[dict, list[str]]:
    from pyshacl import validate
    from rdflib import Graph, Namespace
    from rdflib.namespace import RDF
    EC = Namespace("https://skb.dev/ontology/evidence-catalog#")
    data = Graph().parse(d / "catalog.ttl", format="turtle")
    vocab = Graph().parse(d / "schema" / "evidence-catalog.ttl", format="turtle")
    shapes = Graph().parse(d / "schema" / "evidence-catalog.shapes.ttl", format="turtle")
    for ext in sorted((d / "schema").glob("*.ttl")):  # 확장 어휘·형상(예: legal.ttl, legal.shapes.ttl)
        if ext.name in ("evidence-catalog.ttl", "evidence-catalog.shapes.ttl"):
            continue
        (shapes if ext.name.endswith(".shapes.ttl") else vocab).parse(ext, format="turtle")
    conforms, _, text = validate(data, shacl_graph=shapes, ont_graph=vocab, inference="none", advanced=True)
    errors: list[str] = []
    if not conforms:
        errors.append("SHACL 위반:\n" + text[:2000])
    rows: collections.Counter = collections.Counter()
    sha = hashlib.sha256()
    n = 0
    with open(d / "chunks.jsonl", "rb") as f:
        for line in f:
            sha.update(line)
            rows[json.loads(line)["source_id"]] += 1
            n += 1
    src: dict[str, int] = {}
    for s in data.subjects(RDF.type, EC.Source):
        src[str(next(data.objects(s, EC.legacySeedPrefix)))] = int(next(data.objects(s, EC.chunkCount)))
        if target is not None:
            for rp in data.objects(s, EC.rawPath):
                if not (target / str(rp)).is_file():
                    errors.append(f"rawPath 파일이 없다: {rp}")
    if target is not None:
        errors.extend(_authorship_recompute_errors(data, target))
    for sid in rows:
        if sid not in src:
            errors.append(f"chunks.jsonl 의 source_id 가 카탈로그에 없다: {sid}")
    for sid, c in src.items():
        if rows.get(sid, 0) != c:
            errors.append(f"청크 수 불일치 {sid}: TTL {c} / JSONL {rows.get(sid, 0)}")
    for cs in data.subjects(RDF.type, EC.ChunkSet):
        if int(next(data.objects(cs, EC.rowCount))) != n:
            errors.append(f"ChunkSet rowCount {next(data.objects(cs, EC.rowCount))} != 실제 {n}")
        if str(next(data.objects(cs, EC.sha256))) != sha.hexdigest():
            errors.append("ChunkSet sha256 이 chunks.jsonl 과 다르다(파일이 바뀌었거나 TTL 을 다시 만들지 않았다)")
    return {"sources": len(src), "chunks": n, "triples": len(data), "shacl_conforms": bool(conforms), "errors": len(errors)}, errors


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="catalog-validate")
    ap.add_argument("--target", default=".", help="KB root")
    ap.add_argument("--dir", default=None, help="카탈로그 디렉토리(기본: layout 의 catalog_dir)")
    a = ap.parse_args(argv)
    target = Path(a.target).resolve()
    d = Path(a.dir) if a.dir else _layout.resolve_layout(target)["catalog_dir"]
    summary, errors = validate_dir(d, target)
    print(json.dumps(summary, ensure_ascii=False))
    for e in errors[:20]:
        print(" -", e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
