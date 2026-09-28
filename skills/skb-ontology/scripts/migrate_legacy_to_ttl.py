#!/usr/bin/env python3
"""One-time migration: legacy LinkML-style YAML -> canonical SKB Turtle.

Input shapes (see tests/fixtures/abox_demo/):

  definition YAML (TBox/RBox, LinkML-flavored):
    id: <ontology id>
    prefixes: {ex: "https://example.org/msm/modeling/", ...}
    default_prefix: ex
    classes:
      Task: {}
      ImageGeneration: {is_a: Task}
      TransformerMLMModel: {description: "..."}
    slots:
      canBeUsedFor: {domain: TransformerMLMModel, range: Task, multivalued: true}

  ABox YAML (instances, optional):
    instances:
      gemma4E4b:
        instance_of: TransformerMLMModel
        canBeUsedFor: [imageGenerationTask]
      imageGenerationTask:
        instance_of: ImageGeneration

Contract (see references/core.md, SKILL.md "Migration boundary"):
  - Dry-run by default; nothing is written unless --apply is given.
  - Every migrated IRI requires at least one --evidence IRI (prov:hadPrimarySource) —
    legacy YAML carries no provenance, so this is supplied explicitly and forced onto
    every declared term.
  - The generated graph is written to an isolated temp mirror of the target domain and
    run through the real `ttl_validate.validate_target` gate (registry/link completeness,
    naming/duplicate audits, and domain SHACL if present) before anything touches the
    real target. Any failure aborts with a report and writes nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import OWL, PROV, XSD, DCTERMS

from ttl_common import SKB, canonical_path, load_graph, semantic_root, shapes_files, write_graph
from ttl_validate import validate_target

XSD_MAP = {
    "string": XSD.string,
    "str": XSD.string,
    "integer": XSD.integer,
    "int": XSD.integer,
    "float": XSD.double,
    "double": XSD.double,
    "decimal": XSD.decimal,
    "boolean": XSD.boolean,
    "bool": XSD.boolean,
    "date": XSD.date,
    "datetime": XSD.dateTime,
    "time": XSD.time,
    "uri": XSD.anyURI,
    "uriorcurie": XSD.anyURI,
}


class MigrationError(ValueError):
    pass


def _namespace(definition: dict[str, Any]) -> Namespace:
    prefixes = definition.get("prefixes") or {}
    default_prefix = definition.get("default_prefix")
    if default_prefix and default_prefix in prefixes:
        base = prefixes[default_prefix]
    else:
        base = definition.get("id") or "urn:skb:migrated:"
    base = str(base)
    if not base.endswith(("#", "/", ":")):
        base = f"{base}#"
    return Namespace(base)


def _term(ns: Namespace, name: str) -> URIRef:
    return URIRef(str(ns) + str(name))


def _add_term(graph: Graph, ontology: URIRef, term: URIRef, *, kind: URIRef, label: str,
              evidence: list[str], comment: str | None = None) -> None:
    if any(graph.triples((term, None, None))):
        raise MigrationError(f"duplicate migration target, IRI already present in graph: {term}")
    graph.add((ontology, SKB.declaresTerm, term))
    graph.add((term, RDF.type, kind))
    graph.add((term, RDFS.label, Literal(label)))
    graph.add((term, DCTERMS.identifier, Literal(label)))
    graph.add((term, SKB.status, Literal("draft")))
    for source in evidence:
        graph.add((term, PROV.hadPrimarySource, URIRef(source)))
    if comment:
        graph.add((term, RDFS.comment, Literal(comment)))


def _reify(graph: Graph, subject: URIRef, predicate: URIRef, obj, evidence: list[str]) -> None:
    graph.add((subject, predicate, obj))
    digest = hashlib.sha256(f"{subject}|{predicate}|{obj}".encode()).hexdigest()[:16]
    statement = URIRef(f"urn:skb:assertion:{digest}")
    graph.add((statement, RDF.type, RDF.Statement))
    graph.add((statement, RDF.subject, subject))
    graph.add((statement, RDF.predicate, predicate))
    graph.add((statement, RDF.object, obj))
    for source in evidence:
        graph.add((statement, PROV.hadPrimarySource, URIRef(source)))


def build_migration(graph: Graph, ontology: URIRef, ns: Namespace, definition: dict[str, Any],
                     abox: dict[str, Any] | None, evidence: list[str]) -> dict[str, int]:
    counts = {"classes": 0, "properties": 0, "individuals": 0, "assertions": 0}
    graph.add((ontology, RDF.type, OWL.Ontology))

    classes: dict[str, Any] = definition.get("classes") or {}
    slots: dict[str, Any] = definition.get("slots") or {}

    for name, attrs in classes.items():
        attrs = attrs or {}
        term = _term(ns, name)
        _add_term(graph, ontology, term, kind=OWL.Class, label=name, evidence=evidence,
                  comment=attrs.get("description"))
        counts["classes"] += 1

    for name, attrs in classes.items():
        attrs = attrs or {}
        is_a = attrs.get("is_a")
        if is_a:
            if is_a not in classes:
                raise MigrationError(f"class {name!r} is_a unknown class {is_a!r}")
            graph.add((_term(ns, name), RDFS.subClassOf, _term(ns, is_a)))

    for name, attrs in slots.items():
        attrs = attrs or {}
        term = _term(ns, name)
        range_name = attrs.get("range")
        domain_name = attrs.get("domain")
        if range_name in classes:
            kind = OWL.ObjectProperty
            range_target = _term(ns, range_name)
        else:
            kind = OWL.DatatypeProperty
            range_target = XSD_MAP.get(str(range_name).lower(), XSD.string)
        _add_term(graph, ontology, term, kind=kind, label=name, evidence=evidence,
                  comment=attrs.get("description"))
        if domain_name:
            if domain_name not in classes:
                raise MigrationError(f"slot {name!r} domain references unknown class {domain_name!r}")
            graph.add((term, RDFS.domain, _term(ns, domain_name)))
        else:
            raise MigrationError(f"slot {name!r} has no domain; cannot derive rdfs:domain")
        graph.add((term, RDFS.range, range_target))
        counts["properties"] += 1

    instances: dict[str, Any] = (abox or {}).get("instances") or {}
    for name, attrs in instances.items():
        attrs = attrs or {}
        term = _term(ns, name)
        instance_of = attrs.get("instance_of")
        if not instance_of:
            raise MigrationError(f"instance {name!r} is missing instance_of")
        if instance_of not in classes:
            raise MigrationError(f"instance {name!r} instance_of unknown class {instance_of!r}")
        _add_term(graph, ontology, term, kind=OWL.NamedIndividual, label=name, evidence=evidence)
        graph.add((term, RDF.type, _term(ns, instance_of)))
        counts["individuals"] += 1

    for name, attrs in instances.items():
        attrs = attrs or {}
        subject = _term(ns, name)
        for key, value in attrs.items():
            if key == "instance_of":
                continue
            if key not in slots:
                raise MigrationError(f"instance {name!r} uses undeclared slot {key!r}")
            predicate = _term(ns, key)
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, str) and item in instances:
                    obj = _term(ns, item)
                else:
                    obj = Literal(item)
                _reify(graph, subject, predicate, obj, evidence)
                counts["assertions"] += 1

    return counts


def self_validate(target: Path, domain: str, graph: Graph) -> list[str]:
    """Write the candidate graph into an isolated temp mirror of `target` and run the
    real TTL-only validator against it. Nothing under `target` is touched."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        for shape_path in shapes_files(target, domain):
            rel = shape_path.relative_to(semantic_root(target))
            dest = tmp_root / "ontology" / "system" / "semantic" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(shape_path, dest)
        write_graph(canonical_path(tmp_root, domain), graph)
        _, _, failures = validate_target(tmp_root, domain)
        return failures


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="one-time migration of legacy LinkML-style YAML into canonical SKB Turtle",
    )
    ap.add_argument("--definition", required=True, type=Path, help="LinkML-style classes/slots YAML")
    ap.add_argument("--abox", type=Path, help="optional instances YAML")
    ap.add_argument("--target", required=True, type=Path, help="repository root")
    ap.add_argument("--domain", required=True)
    ap.add_argument("--ontology", help="override the owl:Ontology IRI")
    ap.add_argument("--evidence", action="append", required=True,
                     help="prov:hadPrimarySource IRI; repeatable; required at least once")
    ap.add_argument("--apply", action="store_true", help="write the canonical Turtle file")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)

    if not args.definition.exists():
        print(f"FAIL: definition YAML not found: {args.definition}", file=sys.stderr)
        return 2
    definition = yaml.safe_load(args.definition.read_text(encoding="utf-8")) or {}
    abox = None
    if args.abox:
        if not args.abox.exists():
            print(f"FAIL: abox YAML not found: {args.abox}", file=sys.stderr)
            return 2
        abox = yaml.safe_load(args.abox.read_text(encoding="utf-8")) or {}

    ns = _namespace(definition)
    ontology = URIRef(args.ontology) if args.ontology else URIRef(
        f"urn:skb:ontology:{args.domain.strip('/').replace('/', ':')}"
    )
    path = canonical_path(args.target, args.domain)
    graph = load_graph([path]) if path.exists() else Graph()

    try:
        counts = build_migration(graph, ontology, ns, definition, abox, args.evidence)
    except MigrationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    failures = self_validate(args.target, args.domain, graph)
    if failures:
        print("FAIL: migrated graph did not pass the TTL-only validator; nothing written", file=sys.stderr)
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    summary = (
        f"migrated {counts['classes']} class(es), {counts['properties']} property/properties, "
        f"{counts['individuals']} individual(s), {counts['assertions']} reified assertion(s) "
        f"into domain {args.domain!r} at namespace {ns}"
    )
    if args.apply:
        write_graph(path, graph)
        print(f"APPLIED: {path}")
        print(summary)
    else:
        print("DRY RUN (pass --apply to write); validator gate passed.")
        print(summary)
        print(graph.serialize(format="turtle"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
