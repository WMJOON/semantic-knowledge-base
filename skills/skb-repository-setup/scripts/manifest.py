"""Scaffold manifest for skb-repository-setup.

Source of truth for the 5-Layer tree that `skb init --apply` produces.
SPEC: skb-repository-setup-SPEC §5.1, §5.3, §6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal


FileKind = Literal["dir", "file_template", "file_template_new", "file_empty", "file_executable"]
MarkerKind = Literal["yaml", "markdown", "shell", "none"]


@dataclass(frozen=True)
class Entry:
    path: str
    kind: FileKind
    template: str | None = None          # relative to templates/
    marker: MarkerKind = "none"
    requires: tuple[str, ...] = field(default_factory=tuple)  # gated options


# v1.1.0 topology — three layers separated by name:
#   evidence/   raw sources and the catalog that describes them
#   ontology/system/semantic/ the TTL-only SSOT (authored semantics)
#   projection/ everything derived from the ontology for humans and tools
BASE_DIRS: tuple[str, ...] = (
    "ontology",
    "ontology/system",
    "ontology/system/semantic",
    "ontology/system/kinetic",
    "ontology/system/dynamic",
    "projection",
    "projection/wikigraph",
    "projection/wikigraph/class",
    "projection/wikigraph/instance",
    "projection/query",
    "projection/table",
    "evidence",
    "evidence/md",
    "evidence/raw",
    "evidence/captures",
    "evidence/graphify",
    "record-archive",
    "record-archive/registry",
    "record-archive/runtime",
    "record-archive/events",
    "record-archive/derived",
    "record-archive/snapshots",
    "record-archive/schema",
    "planning",
    "planning/research",
    "planning/ontology",
    "report",
    "report/paper",
    "docs",
    "docs/guideline",
    "agent-context",
    "agent-context/index",
    "agent-context/workflow",
    "agent-context/workflow/evidence",
    "agent-context/workflow/ontology",
    "agent-context/workflow/maintain",
    "agent-context/workflow/explorer",
    "agent-context/work-memory",
    "agent-context/work-memory/auditlog",
    "agent-context/work-memory/worklog",
    "agent-context/work-memory/track-record",
    "agent-context/work-memory/insight-record",
    "harness",
    "harness/tiers",
    "harness/tiers/L0_static",
    "harness/tiers/L1_fixture",
    "harness/tiers/L2_integration",
    "harness/tiers/L3_eval",
    "harness/fixtures",
    "harness/trajectory",
    "harness/reports",
    "harness/oracle",
    ".msm-context",
    ".msm-context/active",
    ".msm-context/archive",
    ".claude",
    ".claude/skills",
    ".claude/hooks",
)


CODEX_DIRS: tuple[str, ...] = (
    ".codex",
    ".codex/skills",
    ".codex/hooks",
)


BASE_FILES: tuple[Entry, ...] = (
    Entry("canonical_root_hub.yaml", "file_template", "canonical_root_hub.yaml", "yaml"),
    Entry("agent-context/index/index.yaml", "file_template", "agent-context/index/index.yaml", "yaml"),
    Entry("agent-context/workflow/index.yaml", "file_template", "agent-context/workflow/index.yaml", "yaml"),
    Entry(
        "agent-context/workflow/evidence/evidence-collection.yaml",
        "file_template",
        "agent-context/workflow/evidence/evidence-collection.yaml",
        "yaml",
    ),
    Entry(
        "agent-context/workflow/ontology/ontology-construction.yaml",
        "file_template",
        "agent-context/workflow/ontology/ontology-construction.yaml",
        "yaml",
    ),
    Entry(
        "agent-context/workflow/maintain/validation.yaml",
        "file_template",
        "agent-context/workflow/maintain/validation.yaml",
        "yaml",
    ),
    Entry(
        "agent-context/workflow/explorer/search-reason.yaml",
        "file_template",
        "agent-context/workflow/explorer/search-reason.yaml",
        "yaml",
    ),
    Entry("docs/index.md", "file_template", "docs/index.md", "markdown"),
    Entry("agent-context/work-memory/index.md", "file_template", "agent-context/work-memory/index.md", "markdown"),
    Entry("harness/run.sh", "file_executable", "harness/run.sh", "shell"),
    Entry(
        "harness/fixtures/repository_setup_minimal.yaml",
        "file_template",
        "harness/fixtures_repository_setup_minimal.yaml",
        "yaml",
    ),
    Entry("evidence/seeds.jsonl", "file_empty", None, "none"),
    Entry("record-archive/registry/instance-ids.jsonl", "file_empty", None, "none"),
)


LAYOUTS = ("b1", "legacy")
DEFAULT_LAYOUT = "b1"

# b1 — 이름만 공개 도구 관례를 따르는 배치. 정본은 계속 TTL 이고, 스킬은 canonical_root_hub.yaml 의
# layout: 섹션으로 경로를 찾는다(템플릿이 그 섹션을 선언한다). legacy 는 layout: 이 없던 이전 배치다.
_B1_DROP_DIRS = {
    "ontology/system/semantic",
    "evidence/md",
    "evidence/raw",
    "agent-context/workflow/evidence",
    "agent-context/workflow/ontology",
    "agent-context/workflow/maintain",
    "agent-context/workflow/explorer",
}
_B1_ADD_DIRS: tuple[str, ...] = (
    "ontology/semantic",
    "evidence/artifact",
    "evidence/artifact/raw",
    "evidence/chunk",
    "evidence/catalog",
)
_LEGACY_ONLY_FILES = {
    "agent-context/workflow/index.yaml",
    "agent-context/workflow/evidence/evidence-collection.yaml",
    "agent-context/workflow/ontology/ontology-construction.yaml",
    "agent-context/workflow/maintain/validation.yaml",
    "agent-context/workflow/explorer/search-reason.yaml",
    "evidence/seeds.jsonl",
    "canonical_root_hub.yaml",
    "agent-context/index/index.yaml",
}
WORKFLOW_TTLS = (
    "workflow-evidence-collection",
    "workflow-ontology-construction",
    "workflow-validation",
    "workflow-search-reason",
)
_B1_FILES: tuple[Entry, ...] = (
    Entry("canonical_root_hub.yaml", "file_template", "canonical_root_hub.b1.yaml", "yaml"),
    *(
        Entry(f"agent-context/workflow/{n}.abox.ttl", "file_template_new", f"agent-context/workflow/{n}.abox.ttl")
        for n in WORKFLOW_TTLS
    ),
    # artifact 레지스트리의 wf:inModule 이 가리키는 층 모듈을 선언한다(MSO artifact 교차층 검증).
    Entry("agent-context/index/index.yaml", "file_template", "agent-context/index/index.b1.yaml", "yaml"),
    Entry("agent-context/index/artifacts.abox.ttl", "file_template_new", "agent-context/index/artifacts.abox.ttl"),
    Entry("evidence/catalog/seeds.jsonl", "file_empty", None, "none"),
    Entry(".gitignore", "file_template_new", "gitignore.template"),
)


def semantic_rel(layout: str = DEFAULT_LAYOUT) -> str:
    return "ontology/semantic" if layout == "b1" else "ontology/system/semantic"


def domain_entries(cluster: str, layout: str = DEFAULT_LAYOUT) -> tuple[Entry, ...]:
    """Create one valid asserted Turtle graph and derived projection folders."""
    semantic = f"{semantic_rel(layout)}/{cluster}"
    hub = f"projection/wikigraph/class/{cluster}"
    return (
        Entry(semantic, "dir"),
        Entry(hub, "dir"),
        Entry(f"projection/wikigraph/instance/{cluster}", "dir"),
        Entry(f"{hub}/{cluster}__class.md", "file_template", "domain_hub.md", "markdown"),
        Entry(f"{semantic}/{cluster}.ttl", "file_template", "ontology/system/semantic/domain.ttl"),
        Entry(f"ontology/system/kinetic/{cluster}.ttl", "file_empty"),
        Entry(f"ontology/system/dynamic/{cluster}.ttl", "file_empty"),
    )


def build_manifest(
    targets: Iterable[str] = ("claude",),
    domain: str | None = None,
    layout: str = DEFAULT_LAYOUT,
) -> list[Entry]:
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout: {layout!r} (choose from {', '.join(LAYOUTS)})")
    out: list[Entry] = []
    if layout == "b1":
        dirs = [d for d in BASE_DIRS if d not in _B1_DROP_DIRS] + list(_B1_ADD_DIRS)
        files = [f for f in BASE_FILES if f.path not in _LEGACY_ONLY_FILES] + list(_B1_FILES)
    else:
        dirs, files = list(BASE_DIRS), list(BASE_FILES)
    out.extend(Entry(p, "dir") for p in dirs)
    if "codex" in targets:
        out.extend(Entry(p, "dir") for p in CODEX_DIRS)
    out.extend(files)
    if domain:
        out.extend(domain_entries(domain, layout))
    return out


MARKER_RE = {
    "yaml": "x_msm_generated:",
    "markdown": "msm:generated:file",
    "shell": "msm:generated:file",
}


def has_marker(content: str, marker: MarkerKind) -> bool:
    if marker == "none":
        return True
    needle = MARKER_RE.get(marker)
    return bool(needle and needle in content)
