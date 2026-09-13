"""Scaffold manifest for skb-repository-setup.

Source of truth for the 5-Layer tree that `skb init --apply` produces.
SPEC: skb-repository-setup-SPEC §5.1, §5.3, §6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal


FileKind = Literal["dir", "file_template", "file_empty", "file_executable"]
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


def domain_entries(cluster: str) -> tuple[Entry, ...]:
    """Create one valid asserted Turtle graph and derived projection folders."""
    semantic = f"ontology/system/semantic/{cluster}"
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
) -> list[Entry]:
    out: list[Entry] = []
    out.extend(Entry(p, "dir") for p in BASE_DIRS)
    if "codex" in targets:
        out.extend(Entry(p, "dir") for p in CODEX_DIRS)
    out.extend(BASE_FILES)
    if domain:
        out.extend(domain_entries(domain))
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
