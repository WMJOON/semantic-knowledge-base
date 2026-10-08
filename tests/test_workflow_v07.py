"""MSO v0.7 (wf:) workflow TTL 를 SKB 파서·라우터·cc_check 가 읽는지 확인한다."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for sub in ("skills/skb-harness/runtime", "skills/skb-orchestration/router", "skills/skb-orchestration/policy"):
    sys.path.insert(0, str(ROOT / sub))

from workflow_ttl import parse_workflow_ttl, scan_workflow_ttls  # noqa: E402
import cc_check  # noqa: E402
import resolve_workflow  # noqa: E402
import workflow_parser  # noqa: E402

WF = """@prefix wf: <https://mso.dev/ontology/workflow#> .
@prefix skbx: <https://skb.dev/ontology/workflow-ext#> .
@prefix t: <https://example.org/t#> .
t:w a wf:Workflow ; wf:has t:start, t:a, t:b, t:ok, t:end ;
    skbx:category "evidence" ; skbx:mode "dry-run" ; skbx:maxRetry 2 ; skbx:oracle "evidence_seed_readiness" ; skbx:oracleThreshold 0.85 .
t:start a wf:Node, wf:Start .
t:end a wf:Node, wf:End .
t:a a wf:Node, wf:Execution, wf:Task ; wf:inWorkflow t:w ; wf:hasSubject "system" ; skbx:tool "skb-evidence" ; skbx:action "ingest" .
t:b a wf:Node, wf:Execution, wf:Task ; wf:inWorkflow t:w ; wf:hasSubject "system" ; skbx:tool "skb-ontology" .
t:ok a wf:Node, wf:Execution, wf:Decision ; wf:inWorkflow t:w ; wf:hasSubject "human" ; wf:hasBranch t:r4, t:r5 .
t:r1 a wf:Edge, wf:Rail ; wf:from t:start ; wf:railType "default" ; wf:to t:a .
t:r2 a wf:Edge, wf:Rail ; wf:from t:a ; wf:railType "default" ; wf:to t:b .
t:r3 a wf:Edge, wf:Rail ; wf:from t:b ; wf:railType "default" ; wf:to t:ok .
t:r4 a wf:Edge, wf:Rail ; wf:from t:ok ; wf:railType "default" ; wf:on "yes" ; wf:to t:end .
t:r5 a wf:Edge, wf:Rail ; wf:from t:ok ; wf:railType "default" ; wf:on "no" ; wf:to t:a .
"""


def _make(tmp_path):
    d = tmp_path / "agent-context" / "workflow"
    d.mkdir(parents=True)
    (d / "workflow-evidence-demo.abox.ttl").write_text(WF, encoding="utf-8")
    return d


def test_parse_v07_contract(tmp_path):
    d = _make(tmp_path)
    meta = parse_workflow_ttl(d / "workflow-evidence-demo.abox.ttl")
    assert meta["id"] == "evidence-demo"
    assert meta["category"] == "evidence" and meta["kind"] == "pipeline"
    assert [s["tool"] for s in meta["pipeline"]] == ["skb-evidence", "skb-ontology"]
    assert meta["pipeline"][0]["action"] == "ingest"
    assert meta["governance"] == {"hitl_required": True, "max_retry": 2, "oracle": "evidence_seed_readiness", "oracle_threshold": 0.85}


def test_parser_and_router_and_cc_check(tmp_path):
    d = _make(tmp_path)
    assert workflow_parser.parse(d / "workflow-evidence-demo.abox.ttl")["id"] == "evidence-demo"
    assert resolve_workflow.resolve(tmp_path, "evidence-demo")["kind"] == "pipeline"
    assert [e["id"] for e in scan_workflow_ttls(d)] == ["evidence-demo"]
    (tmp_path / "canonical_root_hub.yaml").write_text("locked: true\n", encoding="utf-8")
    res = cc_check.check_registry_alignment(tmp_path)
    assert res == []
    assert cc_check.check_workflow_id_uniqueness(tmp_path) == []
