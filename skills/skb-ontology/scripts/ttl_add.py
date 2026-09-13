#!/usr/bin/env python3
"""Add a class, property, individual, or assertion directly to canonical Turtle."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from rdflib import Graph, Literal, RDF, RDFS, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, SKOS

from ttl_common import SKB, canonical_path, load_graph, write_graph
from ttl_validate import audit

KINDS = {
    "class": OWL.Class,
    "object-property": OWL.ObjectProperty,
    "datatype-property": OWL.DatatypeProperty,
    "annotation-property": OWL.AnnotationProperty,
    "individual": OWL.NamedIndividual,
    "concept": SKOS.Concept,
}

SKOS_LINKS = {
    SKOS.related,
    SKOS.broader,
    SKOS.narrower,
    SKOS.exactMatch,
    SKOS.closeMatch,
    SKOS.broadMatch,
    SKOS.narrowMatch,
    SKOS.relatedMatch,
}


def _iri(value: str) -> URIRef:
    if "://" not in value and not value.startswith("urn:"):
        raise ValueError(f"full IRI required: {value!r}")
    return URIRef(value)


def build_change(args: argparse.Namespace) -> tuple[Path, Graph]:
    path = canonical_path(args.target, args.domain)
    graph = load_graph([path]) if path.exists() else Graph()
    ontology = _iri(args.ontology or f"urn:skb:ontology:{args.domain.strip('/').replace('/', ':')}")
    graph.add((ontology, RDF.type, OWL.Ontology))

    if args.kind == "triple":
        subject, predicate, obj = _iri(args.source), _iri(args.predicate), _iri(args.object)
        if (predicate, RDF.type, OWL.ObjectProperty) not in graph and predicate not in SKOS_LINKS:
            raise ValueError(f"predicate must be a declared owl:ObjectProperty or supported SKOS link: {predicate}")
        graph.add((subject, predicate, obj))
        digest = hashlib.sha256(f"{subject}|{predicate}|{obj}".encode()).hexdigest()[:16]
        statement = URIRef(f"urn:skb:assertion:{digest}")
        graph.add((statement, RDF.type, RDF.Statement))
        graph.add((statement, RDF.subject, subject))
        graph.add((statement, RDF.predicate, predicate))
        graph.add((statement, RDF.object, obj))
        for evidence in args.evidence:
            graph.add((statement, PROV.hadPrimarySource, _iri(evidence)))
        return path, graph

    term = _iri(args.iri)
    if any(graph.triples((term, None, None))):
        raise ValueError(f"IRI already exists: {term}")
    graph.add((ontology, SKB.declaresTerm, term))
    graph.add((term, RDF.type, KINDS[args.kind]))
    graph.add((term, RDFS.label, Literal(args.label, lang=args.lang)))
    if args.kind == "concept":
        graph.add((term, SKOS.prefLabel, Literal(args.label, lang=args.lang)))
    graph.add((term, DCTERMS.identifier, Literal(args.identifier or str(term))))
    graph.add((term, SKB.status, Literal(args.status)))
    for evidence in args.evidence:
        graph.add((term, PROV.hadPrimarySource, _iri(evidence)))
    if args.kind == "individual":
        if not args.type:
            raise ValueError("--type is required for individual")
        for class_iri in args.type:
            graph.add((term, RDF.type, _iri(class_iri)))
    if args.kind in {"object-property", "datatype-property"}:
        if not args.domain_class or not args.range:
            raise ValueError("--domain-class and --range are required for properties")
        graph.add((term, RDFS.domain, _iri(args.domain_class)))
        graph.add((term, RDFS.range, _iri(args.range)))
    return path, graph


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="write directly to a canonical SKB Turtle graph")
    ap.add_argument("--target", required=True, type=Path)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--kind", required=True, choices=[*KINDS, "triple"])
    ap.add_argument("--ontology")
    ap.add_argument("--iri")
    ap.add_argument("--label")
    ap.add_argument("--lang", default="ko")
    ap.add_argument("--identifier")
    ap.add_argument("--status", choices=["draft", "accepted", "stable", "deprecated"], default="draft")
    ap.add_argument("--evidence", action="append", required=True)
    ap.add_argument("--type", action="append")
    ap.add_argument("--domain-class")
    ap.add_argument("--range")
    ap.add_argument("--source")
    ap.add_argument("--predicate")
    ap.add_argument("--object")
    ap.add_argument("--apply", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.kind == "triple":
        if not all((args.source, args.predicate, args.object)):
            print("FAIL: triple requires --source, --predicate, and --object", file=sys.stderr)
            return 2
    elif not all((args.iri, args.label)):
        print("FAIL: term requires --iri and --label", file=sys.stderr)
        return 2
    try:
        path, graph = build_change(args)
        failures = audit(graph)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    if args.apply:
        write_graph(path, graph)
        print(path)
    else:
        print(graph.serialize(format="turtle"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
