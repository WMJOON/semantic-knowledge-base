#!/usr/bin/env python3
"""Materialize OWL-RL graph differences as a derived Turtle projection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rdflib import Graph

from ttl_common import asserted_files, load_graph, semantic_root, write_graph
from ttl_validate import validate_target


def inferred_path(target: Path, domain: str) -> Path:
    clean = domain.strip("/")
    name = Path(clean).name
    return semantic_root(target) / clean / f"{name}.inferred.ttl"


def reason(target: Path, domain: str) -> Graph:
    try:
        from owlrl import DeductiveClosure, OWLRL_Semantics
    except ImportError as exc:
        raise RuntimeError("owlrl is required for TTL reasoning") from exc
    asserted = load_graph(asserted_files(target, domain))
    expanded = Graph()
    for triple in asserted:
        expanded.add(triple)
    DeductiveClosure(OWLRL_Semantics, axiomatic_triples=False, datatype_axioms=False).expand(expanded)
    inferred = Graph()
    for triple in expanded:
        if triple not in asserted:
            inferred.add(triple)
    return inferred


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="reason over asserted TTL and emit inferred TTL")
    ap.add_argument("--target", required=True, type=Path)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    _, _, failures = validate_target(args.target, args.domain)
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    try:
        graph = reason(args.target, args.domain)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    path = inferred_path(args.target, args.domain)
    if args.apply:
        write_graph(path, graph)
        print(path)
    else:
        print(graph.serialize(format="turtle"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
