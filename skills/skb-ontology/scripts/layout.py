#!/usr/bin/env python3
"""skb-ontology layout — repo별 ontology/ 디렉토리 관례를 canonical_root_hub.yaml의
layout: 섹션에서 읽어온다 (core.md addendum §7.2 "canonical 위치는 canonical_root_hub.yaml이
선언한 경로를 따른다"의 실제 구현).

fail-soft 3단계 (byte-identical invariant — layout: 섹션이 없는 모든 기존 repo는
이 모듈 도입 전과 완전히 동일한 경로를 돌려받는다):
  1. canonical_root_hub.yaml 이 없음   -> 하드코딩 기본값
  2. 있으나 YAML 파싱 실패             -> 하드코딩 기본값 + 경고 1줄(stderr)
  3. 있고 layout: 섹션이 있음          -> 선언된 키만 기본값을 덮어씀 (키 단위 병합)

canonical_root_hub.yaml의 domains.*.tbox/concept/abox 키(소비자 KB 관례,
scan_orphans.py가 읽음)와는 별개의 최상위 layout: 키를 쓴다 — 두 소비자가 같은 키를
다른 의미로 읽는 충돌을 피하기 위함.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is a listed skill dependency
    yaml = None

_DEFAULTS: dict[str, tuple[str, ...]] = {
    "definition_dir": ("ontology", "definition"),
    "owl_dir": ("ontology", "owl"),
    "abox_dir": ("ontology", "Abox"),
    "tbox_dir": ("ontology", "Tbox"),
    "rbox_dir": ("ontology", "Rbox"),
    "semantic_dir": ("ontology", "system", "semantic"),
    "explain_dir": ("ontology", "explain"),
    "inferred_dir": ("ontology", "Abox", "_inferred"),
    # v0.15.0 — projection/evidence layers plus the md and graph splits.
    #
    # Every default below reproduces the path the pre-v0.15.0 code computed
    # inline, so a repo with no layout: section is unaffected. tbox_md_dir and
    # abox_md_dir are LITERAL tuples rather than aliases of the resolved
    # tbox_dir/abox_dir: aliasing would silently drag a repo's markdown along
    # when it overrides only abox_dir. A repo that moves abox_dir and wants its
    # md co-located must declare abox_md_dir too.
    "tbox_md_dir": ("ontology", "Tbox"),
    "abox_md_dir": ("ontology", "Abox"),
    # reason merges TBox+ABox TTL; when a repo splits them, it declares both
    # owl_dir and abox_owl_dir and reason globs the union (core.md §7.3).
    "abox_owl_dir": ("ontology", "owl"),
    "queries_dir": ("ontology", "queries"),
    "skos_dir": ("ontology", "glossary"),
    "table_dir": ("projection", "table"),
}


def read_layout_section(target: Path, skill: str = "skb-ontology") -> dict:
    """canonical_root_hub.yaml의 layout: 섹션을 raw dict로 읽는다.

    fail-soft 3단계를 여기 한 곳에 둔다. 키 집합은 스킬마다 다르므로
    (skb-ontology는 ontology/, skb-evidence는 evidence/) 해석은 호출자 몫이고,
    이 함수는 파일 읽기와 실패 처리만 소유한다. 복사본이 갈라지는 것을 막기
    위해 다른 skb-* 스킬도 이 함수를 임포트해 쓴다.
    """
    hub_path = Path(target).resolve() / "canonical_root_hub.yaml"
    if not hub_path.exists():
        return {}

    if yaml is None:
        # PyYAML 없이도 선언된 layout: 을 조용히 무시하지 않도록 평면 블록만 읽는다.
        return _read_flat_layout(hub_path, skill)

    try:
        config = yaml.safe_load(hub_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(
            f"[{skill}] canonical_root_hub.yaml 파싱 실패, 기본 경로 사용: {exc}",
            file=sys.stderr,
        )
        return {}

    declared = config.get("layout") if isinstance(config, dict) else None
    return declared if isinstance(declared, dict) else {}


def _read_flat_layout(hub_path: Path, skill: str) -> dict:
    """PyYAML이 없을 때 최상위 `layout:` 블록의 `key: value` 줄만 읽는다."""
    declared: dict[str, str] = {}
    in_block = False
    for raw in hub_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            in_block = raw.split("#", 1)[0].strip() == "layout:"
            continue
        if in_block and ":" in raw:
            key, _, value = raw.partition(":")
            value = value.split(" #", 1)[0].strip().strip("'\"")
            if value:
                declared[key.strip()] = value
    if declared:
        print(
            f"[{skill}] PyYAML 없음: canonical_root_hub.yaml 의 layout: 을 단순 파서로 읽음",
            file=sys.stderr,
        )
    return declared


def apply_declared(target: Path, defaults: dict, declared: dict) -> dict[str, Path]:
    """defaults(키 -> 경로 튜플)에 declared를 키 단위로 덮어써 절대 Path dict 반환."""
    target = Path(target).resolve()
    layout = {key: target.joinpath(*parts) for key, parts in defaults.items()}
    for key in defaults:
        value = declared.get(key)
        if not value:
            continue
        p = Path(str(value))
        layout[key] = p if p.is_absolute() else (target / p)
    return layout


def resolve_layout(target: Path) -> dict[str, Path]:
    """target repo의 layout 딕셔너리(키 -> 절대 Path)를 반환한다."""
    return apply_declared(target, _DEFAULTS, read_layout_section(target))
