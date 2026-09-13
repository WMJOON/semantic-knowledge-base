#!/usr/bin/env python3
"""List classes, properties, and individuals from canonical Turtle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rdflib import RDF, RDFS
from rdflib.namespace import DCTERMS, OWL, PROV

from ttl_common import SKB, asserted_files, load_graph

KIND_MAP = {
    OWL.Class: "class",
    OWL.ObjectProperty: "object-property",
    OWL.DatatypeProperty: "datatype-property",
    OWL.AnnotationProperty: "annotation-property",
    OWL.NamedIndividual: "individual",
}


def records(target: Path, domain: str | None = None) -> list[dict]:
    graph = load_graph(asserted_files(target, domain))
    result: list[dict] = []
    for term in sorted(set(graph.objects(None, SKB.declaresTerm)), key=str):
        kinds = sorted({KIND_MAP[kind] for kind in graph.objects(term, RDF.type) if kind in KIND_MAP})
        result.append({
            "iri": str(term),
            "kind": kinds,
            "identifier": str(graph.value(term, DCTERMS.identifier) or ""),
            "label": str(graph.value(term, RDFS.label) or ""),
            "status": str(graph.value(term, SKB.status) or ""),
            "source_refs": sorted(map(str, graph.objects(term, PROV.hadPrimarySource))),
        })
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="list terms from canonical SKB Turtle")
    ap.add_argument("--target", required=True, type=Path)
    ap.add_argument("--domain")
    ap.add_argument("--kind", choices=sorted(set(KIND_MAP.values())))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows = records(args.target, args.domain)
    if args.kind:
        rows = [row for row in rows if args.kind in row["kind"]]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(f"{','.join(row['kind'])}\t{row['iri']}\t{row['label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
