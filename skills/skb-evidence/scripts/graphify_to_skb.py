#!/usr/bin/env python3
"""
graphify_to_skb.py — Graphify → MSM Semantic Lifting Adapter (Option A)

Pipeline:
  graphify-out/graph.json
      → filter file_type == "concept"  OR  god node code (degree > mean + sigma*std)
      → god node detection → hub_candidate tag
      → entity_candidates.jsonl + relation_candidates.jsonl

  --code-god-nodes flag: LLM semantic extraction 없이 AST-only graph에서도
  동작. god node code 심볼을 CodeSymbol 타입으로 변환.

Usage:
  python graphify_to_skb.py graphify-out/graph.json
  python graphify_to_skb.py graphify-out/graph.json --output-dir etl-out --sigma 2.0
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidate_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", s.lower()).strip("_")


def _source_doc_id(node: dict) -> str:
    sf = node.get("source_file", "")
    if sf:
        return "graphify__" + _slugify(Path(sf).stem)
    return "graphify__unknown"


def _evidence_span(node: dict) -> str:
    sf = node.get("source_file", "unknown")
    label = node.get("label", node["id"])
    return f"graphify:{sf}:{label}"


def _edge_endpoints(edge: dict) -> tuple[str, str]:
    src = edge.get("source") or edge.get("from", "")
    tgt = edge.get("target") or edge.get("to", "")
    return src, tgt


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _god_node_ids(concept_ids: set[str], edges: list[dict], sigma: float) -> set[str]:
    degree: Counter[str] = Counter({nid: 0 for nid in concept_ids})
    for edge in edges:
        src, tgt = _edge_endpoints(edge)
        if src in concept_ids:
            degree[src] += 1
        if tgt in concept_ids:
            degree[tgt] += 1

    if not degree:
        return set()

    values = list(degree.values())
    mean = sum(values) / len(values)
    std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    threshold = mean + sigma * std
    return {nid for nid, d in degree.items() if d > threshold}


def _code_symbol_type(label: str) -> str:
    """Infer entity type from code symbol label heuristics."""
    l = label.lower()
    if l.endswith("adapter"): return "Adapter"
    if l.endswith("runner"): return "Runner"
    if l.endswith("config"): return "Config"
    if l.endswith("db") or l.endswith("store"): return "DataStore"
    if l.endswith("cli"): return "CLI"
    if l.endswith("agent"): return "Agent"
    if l.endswith("event"): return "Event"
    if l.endswith("session"): return "Session"
    if l.endswith("plugin"): return "Plugin"
    if l.endswith("manager"): return "Manager"
    return "CodeSymbol"


def convert(
    graph_path: Path,
    output_dir: Path,
    sigma: float = 2.0,
    include_code_god_nodes: bool = False,
) -> dict[str, int]:
    raw = json.loads(graph_path.read_text(encoding="utf-8"))

    nodes: list[dict] = raw.get("nodes", [])
    edges: list[dict] = raw.get("edges") or raw.get("links", [])

    # --- filter: concept nodes ---
    concept_nodes = {
        n["id"]: n for n in nodes if n.get("file_type") == "concept"
    }

    # --- code god nodes (AST-only graph fallback) ---
    code_god_nodes: dict[str, dict] = {}
    if include_code_god_nodes or not concept_nodes:
        code_nodes = {n["id"]: n for n in nodes if n.get("file_type") == "code"}
        god_ids = _god_node_ids(set(code_nodes), edges, sigma)
        code_god_nodes = {nid: code_nodes[nid] for nid in god_ids}
        if code_god_nodes and not concept_nodes:
            print(
                f"[graphify_to_skb] INFO: no concept nodes — using {len(code_god_nodes)} "
                "code god nodes as CodeSymbol entities (AST-only mode).",
                file=sys.stderr,
            )

    # combined candidate set
    candidate_nodes = {**concept_nodes, **code_god_nodes}

    if not candidate_nodes:
        print("[graphify_to_skb] WARNING: no candidate nodes found.", file=sys.stderr)

    hub_ids = _god_node_ids(set(concept_nodes) or set(code_god_nodes), edges, sigma)

    # --- entity candidates ---
    entity_rows: list[dict] = []
    for node_id, node in candidate_nodes.items():
        is_code = node.get("file_type") == "code"
        tags = ["hub_candidate"] if node_id in hub_ids else []
        if is_code:
            tags.append("code_symbol")
        label = node.get("label", node_id)
        entity_rows.append({
            "candidate_id": _candidate_id(f"graphify:{node_id}"),
            "entity_id": _slugify(node_id),
            "entity_type": _code_symbol_type(label) if is_code else "Concept",
            "label_en": label,
            "label_ko": "",
            "aliases": [],
            "evidence_spans": [_evidence_span(node)],
            "source_doc_id": _source_doc_id(node),
            "confidence": 0.75 if is_code else 0.8,
            "source_refs": [],
            "relations": [],
            "tags": tags,
            "extra": {
                "leiden_community": node.get("community"),
                "leiden_community_name": node.get("community_name", ""),
                "source_file": node.get("source_file", ""),
                "graphify_source": str(graph_path),
            },
        })

    # --- relation candidates (candidate↔candidate edges only) ---
    relation_rows: list[dict] = []
    for edge in edges:
        src, tgt = _edge_endpoints(edge)
        if src not in candidate_nodes or tgt not in candidate_nodes:
            continue
        sf = edge.get("source_file", "unknown")
        relation_rows.append({
            "candidate_id": _candidate_id(
                f"graphify:{src}:{tgt}:{edge.get('relation', '')}"
            ),
            "source_entity_id": _slugify(src),
            "predicate": edge.get("relation") or "related_to",
            "target_entity_id": _slugify(tgt),
            "evidence_spans": [f"graphify:{sf}:{src}→{tgt}"],
            "confidence": float(edge.get("confidence", 0.7)) if isinstance(edge.get("confidence"), (int, float)) else 0.7,
        })

    # --- write ---
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "entity_candidates.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in entity_rows) + "\n",
        encoding="utf-8",
    )
    (output_dir / "relation_candidates.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in relation_rows) + "\n",
        encoding="utf-8",
    )

    stats = {
        "total_nodes": len(nodes),
        "concept_nodes": len(concept_nodes),
        "code_god_nodes": len(code_god_nodes),
        "hub_candidates": len(hub_ids),
        "relations": len(relation_rows),
    }
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Graphify → MSM Semantic Lifting Adapter"
    )
    parser.add_argument(
        "graph_json",
        type=Path,
        help="Path to graphify-out/graph.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("msm-etl-out"),
        help="Output directory (default: msm-etl-out/)",
    )
    parser.add_argument(
        "--sigma",
        type=float,
        default=2.0,
        help="God node threshold in std-dev units (default: 2.0)",
    )
    parser.add_argument(
        "--code-god-nodes",
        action="store_true",
        help="AST-only mode: include code god nodes as CodeSymbol entities",
    )
    args = parser.parse_args()

    if not args.graph_json.exists():
        sys.exit(f"[graphify_to_skb] ERROR: {args.graph_json} not found")

    stats = convert(
        args.graph_json, args.output_dir,
        sigma=args.sigma,
        include_code_god_nodes=args.code_god_nodes,
    )

    print(f"[graphify_to_skb] input nodes   : {stats['total_nodes']}")
    print(f"[graphify_to_skb] concept nodes : {stats['concept_nodes']}")
    print(f"[graphify_to_skb] code god nodes: {stats['code_god_nodes']}")
    print(f"[graphify_to_skb] hub_candidates: {stats['hub_candidates']}")
    print(f"[graphify_to_skb] relations     : {stats['relations']}")
    print(f"[graphify_to_skb] output → {args.output_dir}/")


if __name__ == "__main__":
    main()
