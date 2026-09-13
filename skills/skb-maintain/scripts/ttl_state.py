#!/usr/bin/env python3
"""Shared TTL-only ontology state for skb-maintain."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from rdflib import RDF, RDFS, Graph, URIRef
from rdflib.namespace import OWL, PROV, SKOS

SKILLS = Path(__file__).resolve().parents[2]
ONTOLOGY_SCRIPTS = SKILLS / "skb-ontology" / "scripts"
sys.path.insert(0, str(ONTOLOGY_SCRIPTS))

from ttl_common import SKB  # noqa: E402
from ttl_validate import SKOS_LINKS, validate_target  # noqa: E402

TERM_TYPES = {
    OWL.Class: "classes",
    OWL.ObjectProperty: "object_properties",
    OWL.DatatypeProperty: "datatype_properties",
    OWL.AnnotationProperty: "annotation_properties",
    OWL.NamedIndividual: "individuals",
    SKOS.Concept: "concepts",
}


def seed_records(target: Path) -> list[dict]:
    for relative in ("evidence/seeds.jsonl", "evidence/catalog/seeds.jsonl"):
        path = target / relative
        if not path.exists():
            continue
        records: list[dict] = []
        for line in path.read_text("utf-8").splitlines():
            try:
                if line.strip():
                    records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records
    return []


def ontology_state(target: Path, domain: str | None = None) -> dict:
    paths, graph, failures = validate_target(target, domain)
    declared = {
        term for term in graph.objects(None, SKB.declaresTerm)
        if isinstance(term, URIRef)
    }
    counts = Counter()
    statuses = Counter()
    for term in declared:
        for rdf_type, key in TERM_TYPES.items():
            if (term, RDF.type, rdf_type) in graph:
                counts[key] += 1
        status = graph.value(term, SKB.status)
        statuses[str(status or "missing")] += 1

    object_properties = set(graph.subjects(RDF.type, OWL.ObjectProperty))
    semantic_predicates = object_properties | SKOS_LINKS | {RDFS.subClassOf}
    relations = {
        (subject, predicate, obj)
        for subject, predicate, obj in graph
        if predicate in semantic_predicates and subject in declared and obj in declared
    }
    connected = {node for subject, _, obj in relations for node in (subject, obj)}
    accepted = {
        term for term in declared
        if str(graph.value(term, SKB.status) or "") in {"accepted", "stable"}
    }
    orphan_terms = sorted(accepted - connected, key=str)
    sourced = sum(1 for term in declared if any(graph.objects(term, PROV.hadPrimarySource)))
    term_count = len(declared)
    return {
        "paths": paths,
        "graph": graph,
        "failures": failures,
        "declared": declared,
        "counts": dict(counts),
        "statuses": dict(statuses),
        "relations": relations,
        "orphan_terms": orphan_terms,
        "evidence_coverage": round(sourced / term_count, 3) if term_count else 1.0,
        "relation_density": round(len(relations) / max(term_count, 1), 3),
    }
