#!/usr/bin/env python3
"""skb-evidence layout — evidence/ 디렉토리 관례를 canonical_root_hub.yaml의
layout: 섹션에서 읽어온다.

YAML 읽기와 fail-soft 처리는 skb-ontology의 `read_layout_section` /
`apply_declared`를 그대로 임포트해 쓴다. 파서를 복사해 두 벌 유지하면 한쪽만
고쳐진 채 갈라지고, 그게 L0 하네스가 경로 이동을 몇 주 동안 놓친 원인이었다
(korean-tax IN-0029). 키 집합만 이 스킬이 소유한다.

layout: 섹션이 없는 repo는 이 모듈 도입 전과 완전히 같은 경로를 돌려받는다.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_ontology_layout():
    """skb-ontology의 layout 모듈을 별도 이름으로 로드한다.

    두 스킬의 모듈 파일명이 똑같이 layout.py 라서 `import layout` 은 sys.path
    선두에 있는 이 파일 자신을 다시 집어 순환 임포트가 된다. 경로를 직접 지정해
    'skb_ontology_layout' 이라는 다른 이름으로 올려야 한다.
    """
    src = (Path(__file__).resolve().parents[2]
           / "skb-ontology" / "scripts" / "layout.py")
    spec = importlib.util.spec_from_file_location("skb_ontology_layout", src)
    if spec is None or spec.loader is None:
        raise ImportError(f"skb-ontology layout 로드 실패: {src}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["skb_ontology_layout"] = mod
    spec.loader.exec_module(mod)
    return mod


_ont = _load_ontology_layout()
apply_declared = _ont.apply_declared
read_layout_section = _ont.read_layout_section

_DEFAULTS: dict[str, tuple[str, ...]] = {
    "seeds_path": ("evidence", "seeds.jsonl"),
    "evidence_md_dir": ("evidence", "md"),
    "raw_dir": ("evidence", "raw"),
    "captures_dir": ("evidence", "captures"),
    "graphify_dir": ("evidence", "graphify"),
    "artifact_dir": ("evidence", "artifact"),
    "catalog_dir": ("evidence", "catalog"),
}


def resolve_layout(target: Path) -> dict[str, Path]:
    """target repo의 evidence layout(키 -> 절대 Path)."""
    declared = read_layout_section(target, skill="skb-evidence")
    return apply_declared(target, _DEFAULTS, declared)


def rel(target: Path, path: Path) -> str:
    """seed 레코드에 저장할 KB-상대 경로 문자열.

    md_path 는 JSONL 레코드 안에 문자열로 박히므로 반드시 target 기준
    상대경로여야 한다 — 절대경로가 들어가면 체크아웃 위치가 바뀌는 순간
    project/verify 가 전부 깨진다.
    """
    target = Path(target).resolve()
    try:
        return str(Path(path).resolve().relative_to(target))
    except ValueError:
        return str(path)
