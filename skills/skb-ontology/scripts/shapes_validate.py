#!/usr/bin/env python3
"""Run SHACL over canonical asserted Turtle without a YAML/JSON registry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ttl_common import asserted_files, load_graph, semantic_root, shapes_files


def validate(data_paths: list[Path], shape_paths: list[Path], inference: str) -> tuple[bool, str]:
    try:
        from pyshacl import validate as pyshacl_validate
    except ImportError as exc:
        raise RuntimeError("pyshacl is required for SHACL validation") from exc
    data_graph = load_graph(data_paths)
    shape_graph = load_graph(shape_paths)
    conforms, _, report = pyshacl_validate(
        data_graph=data_graph,
        shacl_graph=shape_graph,
        inference=inference,
        abort_on_first=False,
        meta_shacl=False,
        advanced=True,
        debug=False,
    )
    return bool(conforms), str(report)


def domains(target: Path) -> list[str]:
    root = semantic_root(target)
    if not root.exists():
        return []
    return sorted({str(path.parent.relative_to(root)) for path in root.rglob("*.shapes.ttl")})


def run_domain(target: Path, domain: str, inference: str) -> int:
    data = asserted_files(target, domain)
    shapes = shapes_files(target, domain)
    if not data:
        print(f"FAIL: no asserted TTL for domain {domain}", file=sys.stderr)
        return 2
    if not shapes:
        print(f"FAIL: no *.shapes.ttl for domain {domain}", file=sys.stderr)
        return 2
    try:
        conforms, report = validate(data, shapes, inference)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    if conforms:
        print(f"PASS {domain}: {len(data)} asserted file(s), {len(shapes)} shape file(s)")
        return 0
    print(f"FAIL {domain}\n{report}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate canonical asserted Turtle with SHACL")
    parser.add_argument("--target", type=Path, default=Path.cwd())
    parser.add_argument("--domain")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--data", type=Path, action="append")
    parser.add_argument("--shapes", type=Path, action="append")
    parser.add_argument("--inference", choices=["none", "rdfs", "owlrl", "both"], default="none")
    args = parser.parse_args(argv)
    target = args.target.resolve()

    if args.data or args.shapes:
        if not (args.data and args.shapes):
            print("FAIL: --data and --shapes must be supplied together", file=sys.stderr)
            return 2
        try:
            conforms, report = validate(args.data, args.shapes, args.inference)
        except Exception as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2
        if conforms:
            print("PASS")
            return 0
        print(f"FAIL\n{report}", file=sys.stderr)
        return 1

    selected = domains(target) if args.all else ([args.domain] if args.domain else [])
    if not selected:
        parser.print_usage(sys.stderr)
        return 2
    failures = [run_domain(target, domain, args.inference) for domain in selected]
    return 0 if all(code == 0 for code in failures) else 1


if __name__ == "__main__":
    raise SystemExit(main())
