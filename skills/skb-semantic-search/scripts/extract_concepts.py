#!/usr/bin/env python3
"""SKOS Concept 와 TBox 요소(owl:Class, rdfs:Class, owl:ObjectProperty, owl:DatatypeProperty)를 JSONL 로 추출한다 (임베딩 입력). rdflib 가 필요하다.

사용: extract_concepts.py --target KB [--out FILE] [--tbox-out FILE]
  기본 출력: <KB>/embedding/kb_concepts.jsonl, <KB>/embedding/kb_tbox.jsonl
읽기 전용이다. 정본 TTL 은 수정하지 않고, 읽다가 실패한 파일은 건너뛰며 목록을 stderr 로 알린다.
숨은 라벨(skos:hiddenLabel)은 화면에는 쓰지 않고 검색 키로만 쓴다.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ss_common as C
from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
TBOX_CLASS = (OWL.Class, RDFS.Class)
TBOX_PROPERTY = (OWL.ObjectProperty, OWL.DatatypeProperty)


def _lang(g, c, pred, lang):
    return sorted({str(o) for o in g.objects(c, pred) if getattr(o, "language", None) == lang})


def _texts(g, c, *preds):
    return sorted({str(o) for p in preds for o in g.objects(c, p)})


def _iris(g, c, pred):
    return sorted({str(o) for o in g.objects(c, pred) if isinstance(o, URIRef)})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--out")
    ap.add_argument("--tbox-out")
    a = ap.parse_args()
    target = Path(a.target).resolve()
    out = Path(a.out) if a.out else target / "embedding" / C.CONCEPTS_JSONL
    tbox_out = Path(a.tbox_out) if a.tbox_out else target / "embedding" / C.TBOX_JSONL
    rows, trows, seen, tseen, failed = [], [], set(), set(), []
    for f in C.semantic_ttl_files(target):
        try:
            g = Graph().parse(f, format="turtle")
        except Exception as e:  # 파싱 실패는 숨기지 않고 보고한다
            failed.append(f"{C.rel_to(target, f)} ({type(e).__name__})")
            continue
        rel = str(C.rel_to(target, f))
        for c in g.subjects(RDF.type, SKOS.Concept):
            if str(c) in seen:
                continue
            seen.add(str(c))
            status = sorted({str(o) for p_, o in g.predicate_objects(c) if str(p_).endswith("#status")})
            scheme = _texts(g, c, SKOS.inScheme)
            rows.append({"iri": str(c), "pref_en": _lang(g, c, SKOS.prefLabel, "en"),
                         "pref_ko": _lang(g, c, SKOS.prefLabel, "ko"), "alt": _texts(g, c, SKOS.altLabel),
                         "hidden": _texts(g, c, SKOS.hiddenLabel), "scope_note": " ".join(_texts(g, c, SKOS.scopeNote)),
                         "status": status[0] if status else "", "scheme": scheme[0] if scheme else "", "file": rel})
        for types, tkind in ((TBOX_CLASS, "class"), (TBOX_PROPERTY, "property")):
            for t in types:
                for c in g.subjects(RDF.type, t):
                    if not isinstance(c, URIRef) or str(c) in tseen:
                        continue
                    tseen.add(str(c))
                    supers = RDFS.subClassOf if tkind == "class" else RDFS.subPropertyOf
                    en = sorted(set(_lang(g, c, SKOS.prefLabel, "en") + _lang(g, c, RDFS.label, "en")))
                    ko = sorted(set(_lang(g, c, SKOS.prefLabel, "ko") + _lang(g, c, RDFS.label, "ko")))
                    if not en and not ko:  # 언어 태그가 없는 라벨은 영문 대표 이름으로 쓴다
                        en = _texts(g, c, RDFS.label, SKOS.prefLabel)[:1]
                    trows.append({"iri": str(c), "tkind": tkind, "pref_en": en, "pref_ko": ko,
                                  "alt": _texts(g, c, SKOS.altLabel), "hidden": _texts(g, c, SKOS.hiddenLabel),
                                  "note": " ".join(_texts(g, c, SKOS.definition, SKOS.scopeNote, RDFS.comment)),
                                  "domain": _iris(g, c, RDFS.domain), "range": _iris(g, c, RDFS.range),
                                  "super": _iris(g, c, supers), "file": rel})
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(tbox_out, "w", encoding="utf-8") as fh:
        for r in trows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    for f in failed:
        print("SKIP", f, file=sys.stderr)
    print(f"concepts={len(rows)} tbox={len(trows)} "
          f"(class={sum(1 for r in trows if r['tkind'] == 'class')}, property={sum(1 for r in trows if r['tkind'] == 'property')}) "
          f"parse_failed={len(failed)} -> {out}, {tbox_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
