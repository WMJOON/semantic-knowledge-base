#!/usr/bin/env python3
"""Fail-closed validation for the asserted TTL-only SKB ontology graph."""

from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

from rdflib import BNode, Graph, Literal, RDF, RDFS, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, SKOS

from ttl_common import SKB, asserted_files, is_standard, load_graph, local_name, shapes_files

CLASS_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
PROPERTY_RE = re.compile(r"^[a-z][A-Za-z0-9]*$")
INDIVIDUAL_RE = re.compile(r"^[a-z][A-Za-z0-9]*$")
TERM_TYPES = (
    OWL.Class,
    OWL.ObjectProperty,
    OWL.DatatypeProperty,
    OWL.AnnotationProperty,
    OWL.NamedIndividual,
    SKOS.Concept,
)
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


def _declared(graph: Graph) -> set[URIRef]:
    return {term for term in graph.objects(None, SKB.declaresTerm) if isinstance(term, URIRef)}


def audit(graph: Graph) -> list[str]:
    failures: list[str] = []
    ontologies = {node for node in graph.subjects(RDF.type, OWL.Ontology) if isinstance(node, URIRef)}
    declared = _declared(graph)
    typed: dict[URIRef, set[URIRef]] = collections.defaultdict(set)
    for kind in TERM_TYPES:
        for term in graph.subjects(RDF.type, kind):
            if isinstance(term, URIRef) and not is_standard(term):
                typed[term].add(kind)

    if not ontologies:
        failures.append("[C0] owl:Ontology declaration missing")
    for term in sorted(set(typed) - declared, key=str):
        failures.append(f"[C1] term is not registered with skb:declaresTerm: {term}")
    for term in sorted(declared - set(typed), key=str):
        failures.append(f"[C2] registry target has no supported RDF type: {term}")

    labels: dict[tuple[str, str], set[URIRef]] = collections.defaultdict(set)
    identifiers: dict[str, set[URIRef]] = collections.defaultdict(set)
    folded: dict[str, set[URIRef]] = collections.defaultdict(set)
    for term in sorted(declared, key=str):
        term_types = typed.get(term, set())
        term_labels = list(graph.objects(term, RDFS.label))
        term_ids = list(graph.objects(term, DCTERMS.identifier))
        sources = list(graph.objects(term, PROV.hadPrimarySource))
        statuses = list(graph.objects(term, SKB.status))
        if len(term_types) != 1:
            failures.append(f"[C6] exactly one registry term kind required: {term}")
        if len(term_labels) != 1:
            failures.append(f"[C3] exactly one rdfs:label required: {term}")
        elif not isinstance(term_labels[0], Literal):
            failures.append(f"[C3] rdfs:label must be a literal: {term}")
        if len(term_ids) != 1:
            failures.append(f"[C4] exactly one dct:identifier required: {term}")
        elif not isinstance(term_ids[0], Literal):
            failures.append(f"[C4] dct:identifier must be a literal: {term}")
        if not sources or any(not isinstance(source, URIRef) for source in sources):
            failures.append(f"[C5] IRI prov:hadPrimarySource required: {term}")
        if len(statuses) != 1 or str(statuses[0]) not in {"draft", "accepted", "stable", "deprecated"}:
            failures.append(f"[C7] exactly one valid skb:status required: {term}")
        if SKOS.Concept in term_types:
            pref_labels = list(graph.objects(term, SKOS.prefLabel))
            if len(pref_labels) != 1 or not isinstance(pref_labels[0], Literal):
                failures.append(f"[C8] SKOS concept requires exactly one literal skos:prefLabel: {term}")
        for label in term_labels:
            normalized = " ".join(str(label).casefold().split())
            labels[(getattr(label, "language", "") or "", normalized)].add(term)
        for identifier in term_ids:
            identifiers[str(identifier).casefold()].add(term)
        folded[str(term).casefold()].add(term)

        name = local_name(term)
        if OWL.Class in term_types and not CLASS_RE.fullmatch(name):
            failures.append(f"[N1] class must be UpperCamelCase: {term}")
        if term_types.intersection({OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty}) and not PROPERTY_RE.fullmatch(name):
            failures.append(f"[N2] property must be lowerCamelCase: {term}")
        if term_types.intersection({OWL.NamedIndividual, SKOS.Concept}) and not INDIVIDUAL_RE.fullmatch(name):
            failures.append(f"[N3] individual or SKOS concept must be lowerCamelCase: {term}")

        for prop_type in (OWL.ObjectProperty, OWL.DatatypeProperty):
            if prop_type in term_types:
                domains = list(graph.objects(term, RDFS.domain))
                ranges = list(graph.objects(term, RDFS.range))
                if len(domains) != 1:
                    failures.append(f"[R1] exactly one rdfs:domain required: {term}")
                if len(ranges) != 1:
                    failures.append(f"[R2] exactly one rdfs:range required: {term}")
                for endpoint in [*domains, *ranges]:
                    if isinstance(endpoint, URIRef) and not is_standard(endpoint) and endpoint not in declared:
                        failures.append(f"[R3] domain/range target is not declared: {term} -> {endpoint}")
                    elif isinstance(endpoint, URIRef) and not is_standard(endpoint) and OWL.Class not in typed.get(endpoint, set()):
                        failures.append(f"[R4] domain/range target is not an owl:Class: {term} -> {endpoint}")
        if OWL.NamedIndividual in term_types:
            asserted_types = {
                value for value in graph.objects(term, RDF.type)
                if isinstance(value, URIRef) and value != OWL.NamedIndividual
            }
            if not asserted_types:
                failures.append(f"[A1] individual requires a declared class type: {term}")
            for class_iri in asserted_types:
                if not is_standard(class_iri) and class_iri not in declared:
                    failures.append(f"[A2] individual type is not a declared class: {term} -> {class_iri}")
                elif not is_standard(class_iri) and OWL.Class not in typed.get(class_iri, set()):
                    failures.append(f"[A3] individual type target is not an owl:Class: {term} -> {class_iri}")

    for (_, label), terms in sorted(labels.items()):
        if len(terms) > 1:
            failures.append(f"[D1] duplicate normalized label {label!r}: {sorted(map(str, terms))}")
    for identifier, terms in sorted(identifiers.items()):
        if len(terms) > 1:
            failures.append(f"[D2] duplicate identifier {identifier!r}: {sorted(map(str, terms))}")
    for _, terms in sorted(folded.items()):
        if len(terms) > 1:
            failures.append(f"[D3] case-folded IRI collision: {sorted(map(str, terms))}")

    object_properties = {term for term, kinds in typed.items() if OWL.ObjectProperty in kinds}
    datatype_properties = {term for term, kinds in typed.items() if OWL.DatatypeProperty in kinds}
    for predicate in sorted({predicate for _, predicate, _ in graph}, key=str):
        if isinstance(predicate, URIRef) and not is_standard(predicate) and predicate not in declared:
            failures.append(f"[L0] custom predicate is not a declared registry term: {predicate}")
    for predicate in sorted(object_properties, key=str):
        for subject, obj in graph.subject_objects(predicate):
            if not isinstance(subject, URIRef) or subject not in declared:
                failures.append(f"[L1] object-property source is not a declared term: {subject} {predicate}")
            if not isinstance(obj, URIRef) or obj not in declared:
                failures.append(f"[L2] dangling object-property target: {subject} {predicate} {obj}")
    for predicate in sorted(SKOS_LINKS, key=str):
        for subject, obj in graph.subject_objects(predicate):
            if not isinstance(subject, URIRef) or subject not in declared:
                failures.append(f"[L4] SKOS link source is not a declared term: {subject} {predicate}")
            if not isinstance(obj, URIRef) or obj not in declared:
                failures.append(f"[L5] dangling SKOS link target: {subject} {predicate} {obj}")
            if SKOS.Concept not in typed.get(subject, set()) or SKOS.Concept not in typed.get(obj, set()):
                failures.append(f"[L6] SKOS semantic link endpoints must be skos:Concept: {subject} {predicate} {obj}")
    for predicate in sorted(datatype_properties, key=str):
        for subject, obj in graph.subject_objects(predicate):
            if not isinstance(obj, Literal):
                failures.append(f"[L3] datatype-property value is not a literal: {subject} {predicate} {obj}")

    for statement in graph.subjects(RDF.type, RDF.Statement):
        if not isinstance(statement, (URIRef, BNode)):
            continue
        if not list(graph.objects(statement, PROV.hadPrimarySource)):
            failures.append(f"[P1] reified assertion lacks prov:hadPrimarySource: {statement}")
        subject = graph.value(statement, RDF.subject)
        predicate = graph.value(statement, RDF.predicate)
        obj = graph.value(statement, RDF.object)
        if None in (subject, predicate, obj) or (subject, predicate, obj) not in graph:
            failures.append(f"[P2] reified assertion does not resolve to an asserted triple: {statement}")
    return failures


def shacl_validate(target: Path, domain: str | None, graph: Graph) -> list[str]:
    paths = shapes_files(target, domain)
    if not paths:
        return []
    try:
        from pyshacl import validate
    except ImportError:
        return ["[S0] pyshacl is required when *.shapes.ttl exists"]
    shapes = load_graph(paths)
    conforms, _, report = validate(graph, shacl_graph=shapes, inference="rdfs", advanced=True)
    return [] if conforms else [f"[S1] SHACL violation\n{report}"]


def validate_target(target: Path, domain: str | None = None) -> tuple[list[Path], Graph, list[str]]:
    paths = asserted_files(target, domain)
    if not paths:
        return paths, Graph(), ["[P0] no asserted TTL graph found"]
    try:
        graph = load_graph(paths)
    except Exception as exc:
        return paths, Graph(), [f"[P1] Turtle parse failed: {exc}"]
    failures = audit(graph)
    if not failures:
        failures.extend(shacl_validate(target, domain, graph))
    return paths, graph, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate the TTL-only SKB ontology graph")
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--domain")
    args = parser.parse_args(argv)
    paths, graph, failures = validate_target(args.target, args.domain)
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print(f"PASS: {len(paths)} asserted TTL file(s), {len(graph)} triples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
