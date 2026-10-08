#!/usr/bin/env python3
"""SKOS Concept 를 JSONL 로 추출한다 (임베딩 입력). rdflib 가 필요하다.

사용: extract_concepts.py --target KB [--out FILE]   (기본 출력: <KB>/embedding/kb_concepts.jsonl)
읽기 전용이다. 정본 TTL 은 수정하지 않고, 읽다가 실패한 파일은 건너뛰며 목록을 stderr 로 알린다.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ss_common as C
from rdflib import Graph, Namespace, RDF

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    target = Path(a.target).resolve()
    out = Path(a.out) if a.out else target / "embedding" / C.CONCEPTS_JSONL
    rows, seen, failed = [], set(), []
    for f in C.semantic_ttl_files(target):
        try:
            g = Graph().parse(f, format="turtle")
        except Exception as e:  # 파싱 실패는 숨기지 않고 보고한다
            failed.append(f"{C.rel_to(target, f)} ({type(e).__name__})")
            continue
        for c in g.subjects(RDF.type, SKOS.Concept):
            if str(c) in seen:
                continue
            seen.add(str(c))
            lab = lambda p, lang=None: sorted({str(o) for o in g.objects(c, p) if lang is None or getattr(o, "language", None) == lang})
            status = sorted({str(o) for p_, o in g.predicate_objects(c) if str(p_).endswith("#status")})
            scheme = lab(SKOS.inScheme)
            rows.append({"iri": str(c), "pref_en": lab(SKOS.prefLabel, "en"), "pref_ko": lab(SKOS.prefLabel, "ko"),
                         "alt": lab(SKOS.altLabel), "scope_note": " ".join(lab(SKOS.scopeNote)),
                         "status": status[0] if status else "", "scheme": scheme[0] if scheme else "",
                         "file": str(C.rel_to(target, f))})
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    for f in failed:
        print("SKIP", f, file=sys.stderr)
    print(f"concepts={len(rows)} with_note={sum(1 for r in rows if r['scope_note'])} parse_failed={len(failed)} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
