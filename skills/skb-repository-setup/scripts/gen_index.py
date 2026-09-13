#!/usr/bin/env python3
"""
gen_index.py — MSM init 시 index.yaml 자동 생성·갱신

동작 규칙:
  1. index.yaml 없음         → MSM 표준 모듈 포함 신규 생성
  2. index.yaml 있음 + 생성 마커 → MSM 모듈 섹션만 병합 (기존 모듈 보존)
  3. index.yaml 있음 + 마커 없음 → skip (사용자 관리 파일, HITL 정책 준수)

mso-scaffold-design v2 스키마 준수 (project + modules 구조).
검증: python sf_node.py validate index.yaml
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

_MARKER_KEY = "x_msm_generated"
_MARKER_VALUE_PREFIX = "skb-repository-setup"
_MSM_MODULE_IDS = {"skb-record-archive", "skb-record-archive", "skb-ontology-layer"}


def _today() -> str:
    return _dt.date.today().isoformat()


def _msm_modules(domain: str | None) -> list[dict]:
    """MSM v0.13.4 표준 모듈 정의."""
    return [
        {
            "id": "skb-record-archive",
            "path": "record-archive/",
            "description": "MSM v0.13.4 — record archive: SQLite runtime DB, events, derived records, snapshots",
            "subdirs": [
                {"path": "registry/", "role": "data",
                 "description": "stable instance id registry"},
                {"path": "runtime/", "role": "runtime",
                 "description": "SQLite runtime DB (OLTP/WAL)"},
                {"path": "events/", "role": "data",
                 "description": "append-only occurrence/change events"},
                {"path": "derived/", "role": "data",
                 "description": "materialized derived state records"},
                {"path": "snapshots/", "role": "output",
                 "description": "Parquet snapshots (DuckDB analytics bridge)"},
            ],
            "key_files": ["registry/instance-ids.jsonl", "runtime/runtime.db"],
            "references": [
                {"consumes": "skb-ontology-layer",
                 "artifacts": ["source_refs", "ontology/system/**/*.ttl"]},
            ],
            "status": "active",
        },
        {
            "id": "skb-ontology-layer",
            "path": "ontology/",
            "description": (
                "MSM v0.13.4 — Ontology layer "
                "(explain Markdown + system Turtle/PROV-O graphs)"
            ),
            "subdirs": [
                {"path": "explain/concept/", "role": "projection",
                 "description": "human-readable Class projection"},
                {"path": "explain/instance/", "role": "projection",
                 "description": "human-readable instance snapshot projection"},
                {"path": "system/semantic/", "role": "graph",
                 "description": "Turtle/RDF/OWL semantic graph + PROV-O projection"},
                {"path": "system/kinetic/", "role": "graph",
                 "description": "Turtle transition/action rule graph"},
                {"path": "system/dynamic/", "role": "graph",
                 "description": "Turtle event/state/derived-value semantic graph"},
            ],
            "status": "active",
        },
    ]


def _scaffold_index(target: Path, name: str, domain: str | None) -> dict:
    """index.yaml 초안 dict 생성."""
    return {
        _MARKER_KEY: {
            "skill":        _MARKER_VALUE_PREFIX,
            "version":      "1.2.0",
            "generated_at": _today(),
        },
        "project": {
            "name":        name,
            "id":          name.lower().replace(" ", "-"),
            "description": f"{name} KB — MSM v0.13.4 record archive 포함.",
            "owner":       "OWNER",
            "updated":     _today(),
            "version":     "1.0.0",
        },
        "modules": _msm_modules(domain),
    }


def _has_marker(data: dict) -> bool:
    marker = data.get(_MARKER_KEY, {})
    if not isinstance(marker, dict):
        return False
    return str(marker.get("skill", "")).startswith(_MARKER_VALUE_PREFIX)


def _merge_msm_modules(existing_modules: list[dict], domain: str | None) -> list[dict]:
    """기존 모듈 리스트에 MSM 모듈을 upsert (id 기준)."""
    kept = [m for m in existing_modules if m.get("id") not in _MSM_MODULE_IDS]
    return kept + _msm_modules(domain)


def gen_or_update_index(
    target: Path,
    name: str | None,
    domain: str | None,
    dry_run: bool = False,
) -> str:
    """
    index.yaml 생성 또는 갱신.
    반환값: "created" | "updated" | "skipped"
    """
    try:
        import yaml  # pyyaml
    except ImportError:
        print("[gen_index] pyyaml 없음 — index.yaml 생성 건너뜀", file=sys.stderr)
        return "skipped"

    index_path = target / "index.yaml"
    proj_name  = name or target.resolve().name

    # ── Case 1: 없음 → 신규 생성 ────────────────────────────────────────────
    if not index_path.exists():
        data = _scaffold_index(target, proj_name, domain)
        if not dry_run:
            index_path.write_text(
                yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
        print(f"[gen_index] created: {index_path}")
        return "created"

    # ── Case 2/3: 있음 → 마커 확인 ──────────────────────────────────────────
    existing = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}

    if not _has_marker(existing):
        print(
            f"[gen_index] skipped: {index_path} (사용자 관리 파일 — 마커 없음)",
            file=sys.stderr,
        )
        return "skipped"

    # ── Case 2: 마커 있음 → MSM 모듈 병합 ──────────────────────────────────
    existing_modules = existing.get("modules", [])
    merged = _merge_msm_modules(existing_modules, domain)
    existing["modules"] = merged
    existing[_MARKER_KEY]["generated_at"] = _today()
    existing[_MARKER_KEY]["version"]      = "1.2.0"

    if not dry_run:
        index_path.write_text(
            yaml.dump(existing, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
    print(f"[gen_index] updated: {index_path} (MSM 모듈 2개 병합)")
    return "updated"


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target",  default=".")
    p.add_argument("--name",    default=None)
    p.add_argument("--domain",  default=None)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    result = gen_or_update_index(Path(a.target), a.name, a.domain, a.dry_run)
    sys.exit(0 if result in ("created", "updated", "skipped") else 1)
