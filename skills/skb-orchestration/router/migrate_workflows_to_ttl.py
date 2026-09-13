#!/usr/bin/env python3
"""Migrate MSM workflow YAML files to TTL ABox SSOT.

YAML remains a migration/edit layer. Runtime code prefers
``agent-context/workflow/index.ttl`` and explicit ``*.abox.ttl`` workflow files
when present. Legacy ``workflow/`` roots are still accepted as migration input.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from workflow_ttl import serialize_index_ttl, serialize_workflow_ttl, workflow_dict_from_yaml_doc


DEFAULT_PATTERNS = ("*.yaml", "*.yml")


def _ttl_path(yaml_path: Path) -> Path:
    return yaml_path.with_suffix(".abox.ttl")


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _iter_workflow_yamls(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    if root.is_file():
        return [] if root.name == "index.yaml" else [root]
    out: list[Path] = []
    for pattern in patterns:
        for path in root.rglob(pattern):
            if path.name == "index.yaml" or "/." in str(path):
                continue
            out.append(path)
    return sorted(set(out))


def _rewrite_index_paths(index_doc: dict, workflow_root: Path) -> list[dict]:
    workflows = []
    for wf in index_doc.get("workflows", []) or []:
        if not isinstance(wf, dict):
            continue
        item = dict(wf)
        path = item.get("path")
        if isinstance(path, str) and path.endswith((".yaml", ".yml")):
            item["path"] = str(Path(path).with_suffix(".abox.ttl"))
        workflows.append(item)
    return workflows


def migrate(root: Path, patterns: tuple[str, ...], check: bool = False) -> int:
    root = root.resolve()
    changed: list[Path] = []

    for yaml_path in _iter_workflow_yamls(root, patterns):
        doc = _load_yaml(yaml_path)
        ttl_text = serialize_workflow_ttl(workflow_dict_from_yaml_doc(doc, yaml_path))
        ttl_path = _ttl_path(yaml_path)
        current = ttl_path.read_text(encoding="utf-8") if ttl_path.exists() else None
        if current != ttl_text:
            changed.append(ttl_path)
            if not check:
                ttl_path.write_text(ttl_text, encoding="utf-8")
                print(f"WRITE {ttl_path}")
        else:
            print(f"OK    {ttl_path}")

    index_yaml = root / "index.yaml" if root.is_dir() else root.parent / "index.yaml"
    if index_yaml.exists():
        index_doc = _load_yaml(index_yaml)
        workflows = _rewrite_index_paths(index_doc, index_yaml.parent)
        ttl_text = serialize_index_ttl(workflows)
        index_ttl = index_yaml.with_suffix(".ttl")
        current = index_ttl.read_text(encoding="utf-8") if index_ttl.exists() else None
        if current != ttl_text:
            changed.append(index_ttl)
            if not check:
                index_ttl.write_text(ttl_text, encoding="utf-8")
                print(f"WRITE {index_ttl}")
        else:
            print(f"OK    {index_ttl}")

    if check and changed:
        print("[ERROR] MSM workflow TTL 정본이 YAML migration layer와 동기화되지 않았습니다:", file=sys.stderr)
        for path in changed:
            print(f"  {path}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skb-workflow-yaml-to-ttl")
    parser.add_argument("root", help="workflow 디렉토리 또는 단일 workflow YAML")
    parser.add_argument("--pattern", action="append", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.exists():
        print(f"[ERROR] 경로 없음: {root}", file=sys.stderr)
        return 2
    return migrate(root, tuple(args.pattern) if args.pattern else DEFAULT_PATTERNS, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
