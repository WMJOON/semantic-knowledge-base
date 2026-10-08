#!/usr/bin/env python3
"""Shared graph discovery and deterministic helpers for TTL-only skb-ontology."""

from __future__ import annotations

import re
from pathlib import Path

from rdflib import Graph, Namespace, URIRef

SKB = Namespace("https://semantic-knowledge-base.dev/ontology#")
STANDARD_PREFIXES = (
    "http://www.w3.org/",
    "https://www.w3.org/",
    "http://purl.org/",
    "https://purl.org/",
    str(SKB),
)


def semantic_root(target: Path) -> Path:
    return Path(target).resolve() / "ontology" / "system" / "semantic"


def canonical_path(target: Path, domain: str) -> Path:
    clean = domain.strip("/")
    if not clean or ".." in Path(clean).parts:
        raise ValueError(f"invalid domain: {domain!r}")
    name = Path(clean).name
    return semantic_root(target) / clean / f"{name}.ttl"


def asserted_files(target: Path, domain: str | None = None) -> list[Path]:
    root = semantic_root(target)
    scope = root / domain.strip("/") if domain else root
    if not scope.exists():
        return []
    return sorted(
        path for path in scope.rglob("*.ttl")
        if not path.name.endswith((".shapes.ttl", ".inferred.ttl"))
    )


def shapes_files(target: Path, domain: str | None = None) -> list[Path]:
    """도메인 범위의 *.shapes.ttl + (도메인 실행일 때) semantic 루트 바로 아래의 KB 전역 shapes.

    루트 직속 shapes(<semantic root>/*.shapes.ttl)는 KB 전체에 적용되는 규약(예: prefLabel/altLabel 관리)이다.
    도메인 범위 검증에서 이를 빼면 전역 규약이 어느 도메인 실행에도 적용되지 않는다.
    """
    root = semantic_root(target)
    scope = root / domain.strip("/") if domain else root
    files = sorted(scope.rglob("*.shapes.ttl")) if scope.exists() else []
    if domain:
        files += [p for p in sorted(root.glob("*.shapes.ttl")) if p not in files]
    return files


def load_graph(paths: list[Path]) -> Graph:
    graph = Graph()
    for path in paths:
        graph.parse(path, format="turtle")
    return graph


def local_name(iri: URIRef) -> str:
    value = str(iri).rstrip("/")
    return re.split(r"[/#]", value)[-1]


def is_standard(iri: URIRef) -> bool:
    return str(iri).startswith(STANDARD_PREFIXES)


def bind_prefixes(graph: Graph) -> None:
    graph.bind("skb", SKB)
    graph.bind("owl", "http://www.w3.org/2002/07/owl#")
    graph.bind("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#")
    graph.bind("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
    graph.bind("dct", "http://purl.org/dc/terms/")
    graph.bind("prov", "http://www.w3.org/ns/prov#")
    graph.bind("skos", "http://www.w3.org/2004/02/skos/core#")
    graph.bind("xsd", "http://www.w3.org/2001/XMLSchema#")


def write_graph(path: Path, graph: Graph) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bind_prefixes(graph)
    graph.serialize(destination=path, format="turtle")
