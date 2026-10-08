"""이 저장소가 싣고 있는 workflow TTL(agent-context/workflow)을 이 저장소의 파서·라우터·계약 검사가 읽는지 확인한다.

PR #1 이 wf:/skbx: 어휘의 TTL 워크플로우를 올렸지만 하네스 파서는 옛 msmwf 어휘만 읽어 id/tool 이 모두 None 이었다.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in ("skills/skb-harness/runtime", "skills/skb-orchestration/router", "skills/skb-orchestration/policy"):
    sys.path.insert(0, str(ROOT / sub))

import cc_check  # noqa: E402
import resolve_workflow  # noqa: E402
import workflow_parser  # noqa: E402
from workflow_ttl import scan_workflow_ttls  # noqa: E402

WF_DIR = ROOT / "agent-context" / "workflow"
LIVE = sorted(p for p in WF_DIR.rglob("workflow-*.abox.ttl"))


def test_repository_ships_workflow_ttls():
    assert len(LIVE) >= 5


def test_every_shipped_workflow_ttl_has_id_and_category():
    for p in LIVE:
        meta = workflow_parser.parse(p)
        assert meta["id"], f"{p.name}: id 를 읽지 못했다"
        assert meta["category"], f"{p.name}: category 를 읽지 못했다"
        steps = meta.get("pipeline") or ([{"tool": meta.get("tool")}] if meta.get("tool") else [])
        assert steps and all(s.get("tool") for s in steps), f"{p.name}: tool 을 읽지 못했다"


def test_scan_finds_all_shipped_workflows():
    assert {m["id"] for m in scan_workflow_ttls(WF_DIR)} >= {"validation", "ontology-construction", "evidence-collection"}


def test_router_resolves_a_shipped_workflow_by_id():
    meta = resolve_workflow.resolve(ROOT, "validation")
    assert meta and meta["category"] == "maintain"


def test_cc_check_finds_no_missing_index_or_pack_violation():
    contracts = {v["contract"] for v in cc_check.check(ROOT)["violations"]}
    assert "workflow_index_present" not in contracts  # index.ttl 없이 workflow-*.abox.ttl 스캔으로 충분하다
    assert "pack_config_core_count" not in contracts


@pytest.mark.xfail(strict=True, reason="agent-context/workflow/evidence 에 옛 msmwf graphify-etl.abox.ttl(테스트용 복원본)과 "
                   "새 workflow-evidence-graphify-etl.abox.ttl 이 같은 id 를 가진다 (changelog v1.3.1 Known issue). 해소되면 이 표시를 지운다.")
def test_cc_check_is_clean_on_the_shipped_tree():
    assert cc_check.check(ROOT)["ok"] is True


def test_the_only_cc_check_violation_is_the_known_duplicate_graphify_id():
    violations = cc_check.check(ROOT)["violations"]
    assert [(v["contract"], v.get("id")) for v in violations] == [("workflow_id_uniqueness", "evidence.graphify.etl")]
