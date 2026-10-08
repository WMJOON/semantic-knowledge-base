"""경로 관례 해석 — canonical_root_hub.yaml 의 layout: 섹션을 읽는다 (skb-graph-reasoning · skb-semantic-search 공용 복사본).

두 스킬이 skb-ontology 없이도 도는 독립성을 지키려고 같은 파일을 각각 둔다.
`tests/test_skb_layout_copies.py` 가 두 복사본이 같은 내용인지 확인한다. 고칠 때는 둘을 함께 고친다.

layout: 이 없는 KB 는 이전과 같은 경로(ontology/system/semantic, evidence/seeds.jsonl)를 돌려받는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

DEFAULT_SEMANTIC_DIR = ("ontology", "system", "semantic")
DEFAULT_SEEDS_PATH = ("evidence", "seeds.jsonl")


def _read_flat(hub: Path) -> dict:
    declared: dict = {}
    in_block = False
    for raw in hub.read_text(encoding="utf-8").splitlines():
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
    return declared


def read_layout(target: Path) -> dict:
    hub = Path(target).resolve() / "canonical_root_hub.yaml"
    if not hub.exists():
        return {}
    if yaml is None:
        return _read_flat(hub)
    try:
        config = yaml.safe_load(hub.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"[skb-layout] canonical_root_hub.yaml 파싱 실패, 기본 경로 사용: {exc}", file=sys.stderr)
        return {}
    declared = config.get("layout") if isinstance(config, dict) else None
    return declared if isinstance(declared, dict) else {}


def _resolve(target: Path, key: str, default: tuple) -> Path:
    target = Path(target).resolve()
    value = read_layout(target).get(key)
    if not value:
        return target.joinpath(*default)
    p = Path(str(value))
    return p if p.is_absolute() else target / p


def semantic_dir(target: Path) -> Path:
    return _resolve(target, "semantic_dir", DEFAULT_SEMANTIC_DIR)


def seeds_path(target: Path) -> Path:
    return _resolve(target, "seeds_path", DEFAULT_SEEDS_PATH)
