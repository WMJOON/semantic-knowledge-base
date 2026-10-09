"""저장소가 싣고 가는 workflow TTL 템플릿(skb-repository-setup/assets/templates)을 이 저장소의 파서·라우터·계약 검사가 읽는지 확인한다.

`skb init` 이 새 KB 에 복사하는 것과 같은 파일이므로, 여기서 통과하면 init 직후의 KB 도 같은 검사를 통과한다.
"""
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "skills" / "skb-repository-setup" / "assets" / "templates"
for sub in ("skills/skb-harness/runtime", "skills/skb-orchestration/router", "skills/skb-orchestration/policy"):
    sys.path.insert(0, str(ROOT / sub))

import cc_check  # noqa: E402
import resolve_workflow  # noqa: E402
import workflow_parser  # noqa: E402
from workflow_ttl import scan_workflow_ttls  # noqa: E402


@pytest.fixture(scope="module")
def kb(tmp_path_factory):
    """init 이 만드는 KB 루트를 템플릿에서 그대로 재현한다."""
    root = tmp_path_factory.mktemp("kb")
    shutil.copytree(TEMPLATES / "agent-context", root / "agent-context")
    shutil.copy(TEMPLATES / "canonical_root_hub.yaml", root / "canonical_root_hub.yaml")
    return root


@pytest.fixture(scope="module")
def live(kb):
    return sorted((kb / "agent-context" / "workflow").rglob("workflow-*.abox.ttl"))


def test_repository_ships_workflow_ttls(live):
    assert len(live) >= 4


def test_every_shipped_workflow_ttl_has_id_and_category(live):
    for p in live:
        meta = workflow_parser.parse(p)
        assert meta["id"], f"{p.name}: id 를 읽지 못했다"
        assert meta["category"], f"{p.name}: category 를 읽지 못했다"
        steps = meta.get("pipeline") or ([{"tool": meta.get("tool")}] if meta.get("tool") else [])
        assert steps and all(s.get("tool") for s in steps), f"{p.name}: tool 을 읽지 못했다"


def test_scan_finds_all_shipped_workflows(kb):
    assert {m["id"] for m in scan_workflow_ttls(kb / "agent-context" / "workflow")} >= {"validation", "ontology-construction", "evidence-collection", "search-reason"}


def test_router_resolves_a_shipped_workflow_by_id(kb):
    meta = resolve_workflow.resolve(kb, "validation")
    assert meta and meta["category"] == "maintain"


def test_cc_check_is_clean_on_the_shipped_templates(kb):
    result = cc_check.check(kb)
    assert result["ok"] is True, result["violations"]
