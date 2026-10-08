#!/usr/bin/env python3
"""List seeds from evidence/seeds.jsonl, or (--catalog) the documents of evidence/catalog/catalog.ttl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as _layout_mod  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="list_seeds")
    p.add_argument("--target", default=".", help="KB root path")
    p.add_argument("--format", choices=["table", "json", "ids"], default="table")
    p.add_argument("--catalog", action="store_true", help="청크 행 대신 카탈로그의 문서 단위 목록(발행자·URL·청크 수·시점)을 보여준다")
    return p.parse_args(argv)


def _list_catalog(target: Path, fmt: str) -> int:
    d = _layout_mod.resolve_layout(target)["catalog_dir"]
    if not (d / "catalog.ttl").is_file():
        print("ERROR: 카탈로그가 없다 — skb-evidence catalog --apply 로 먼저 만든다", file=sys.stderr)
        return 1
    from rdflib import Graph, Namespace
    from rdflib.namespace import DCTERMS, RDF, SKOS
    EC = Namespace("https://skb.dev/ontology/evidence-catalog#")
    PROV = Namespace("http://www.w3.org/ns/prov#")
    g = Graph().parse(d / "catalog.ttl", format="turtle")
    one = lambda s, p: next((str(o) for o in g.objects(s, p)), None)  # noqa: E731
    docs = []
    for s in g.subjects(RDF.type, EC.Source):
        pub = next(g.objects(s, DCTERMS.publisher), None)
        r = next(g.objects(s, PROV.wasGeneratedBy), None)
        docs.append({"source": one(s, EC.legacySeedPrefix), "title": one(s, DCTERMS.title),
                     "publisher": (one(pub, SKOS.prefLabel) or str(pub).rsplit("/", 1)[-1]) if pub else None,
                     "url": one(s, DCTERMS.source) or one(s, EC.legacyUri), "chunks": int(one(s, EC.chunkCount) or 0),
                     "retrieved_at": one(r, EC.retrievedAt) if r else None, "searched_at": one(r, EC.searchedAt) if r else None,
                     "authorship": one(s, EC.authorshipState)})
    docs.sort(key=lambda x: x["source"] or "")
    if fmt == "json":
        json.dump(docs, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    elif fmt == "ids":
        for x in docs:
            print(x["source"])
    else:
        print(f"{'SOURCE':<44} {'PUBLISHER':<18} {'CHUNKS':>6} {'RETRIEVED':<20} {'SEARCHED':<20} URL")
        print("-" * 140)
        for x in docs:
            print(f"{(x['source'] or '')[:43]:<44} {(x['publisher'] or '')[:17]:<18} {x['chunks']:>6} {(x['retrieved_at'] or '')[:19]:<20} {(x['searched_at'] or '-')[:19]:<20} {x['url'] or ''}")
        print(f"\nTotal: {len(docs)} source(s), {sum(x['chunks'] for x in docs)} chunk(s)")
    return 0


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    target = Path(args.target).resolve()
    if args.catalog:
        return _list_catalog(target, args.format)
    seeds_path = _layout_mod.resolve_layout(target)["seeds_path"]

    if not seeds_path.exists():
        print("(no seeds.jsonl found)")
        return 0

    seeds: list[dict] = []
    with seeds_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                seeds.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if not seeds:
        print("(empty seeds.jsonl — 0 seeds)")
        return 0

    fmt = args.format
    if fmt == "json":
        json.dump(seeds, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    elif fmt == "ids":
        for s in seeds:
            print(s.get("id", ""))
    else:
        # Table
        print(f"{'ID':<45} {'KIND':<5} {'STATUS':<12} {'HASH':<16}")
        print("-" * 85)
        for s in seeds:
            sid = s.get("id", "")[:44]
            kind = s.get("kind", "")[:4]
            status = s.get("status", "")[:11]
            ch = s.get("content_hash", "")
            ch_short = ch[:16] if ch else ""
            print(f"{sid:<45} {kind:<5} {status:<12} {ch_short}")
        print(f"\nTotal: {len(seeds)} seed(s)")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
