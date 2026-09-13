"""MSM workflow ↔ MSO 레이어링 가드 (UD-0004).

MSM workflow 는 MSO mso-workflow-design 을 **구조 기준**으로 소비한다:
  · `module:` + named phase(step.label/instruction/directories) = MSO 구조
  · `x_msm:` = MSM 실행 계약(category/kind/mode/tool/pipeline/governance)

이 파일은 두 가지를 잠근다:
  1. **파서 라운드트립** (MSO 불필요 — 항상 실행): 변환된 워크플로를 MSM 의 두 regex
     파서(workflow_parser·workflow_meta)로 다시 읽어 kind/mode/category/tool/
     governance 가 silent-None 없이 정확히 복원되는지. MSO 구조 검증이 green 이어도
     MSM 이 x_msm 을 못 읽으면 실행이 조용히 죽는 실패모드를 차단한다.
  2. **구조 검증 위임** (MSO 부재 시 skip): 모든 MSM workflow yaml 이 현재 MSO
     wf_node(schema) + wf_to_ttl(SHACL/DAG) 를 통과하는지. 실패 = MSO 스키마 drift
     → graphify-etl(또는 변환 규칙) 동기화 필요.

실행: python3 -m pytest tests/ -q   (pyyaml; 구조검증엔 rdflib/pyshacl 권장)
"""
import subprocess
import sys
from pathlib import Path

import pytest

# parents: [0]tests [1]skb-repository-setup [2]skills [3]repository
#          [4]11_semantic-knowledge-base [5]integration repository root
_REPO = Path(__file__).resolve().parents[3]
_MONOREPO = Path(__file__).resolve().parents[5]
_MSO_SCRIPTS = (
    _MONOREPO
    / "00_multi-swarm-orchestrator/repository/skills/mso-workflow-design/scripts"
)
_WF_DIR = _REPO / "agent-context" / "workflow"


def _workflow_yamls() -> list[Path]:
    return sorted(p for p in _WF_DIR.rglob("*.yaml") if p.name != "index.yaml")


def _import_parsers():
    sys.path.insert(0, str(_REPO / "skills" / "skb-harness" / "runtime"))
    sys.path.insert(0, str(_REPO / "skills" / "skb-orchestration" / "policy"))
    import workflow_meta  # noqa: WPS433
    import workflow_parser  # noqa: WPS433
    return workflow_parser, workflow_meta


# ── 1. 파서 라운드트립 (항상 실행) ────────────────────────────────────────────
def test_converted_workflow_parser_roundtrip():
    """변환된 graphify-etl 이 MSM 파서로 silent-None 없이 복원돼야 한다."""
    wf = _WF_DIR / "evidence" / "graphify-etl.yaml"
    assert wf.exists(), f"기준 워크플로 부재: {wf}"
    workflow_parser, workflow_meta = _import_parsers()

    p = workflow_parser.parse(wf)
    assert p["kind"] == "single", p["kind"]
    assert p["mode"] == "dry-run", p["mode"]
    assert p["category"] == "evidence", p["category"]
    assert p["tool"] == "skb-evidence", p["tool"]
    assert p["id"] == "evidence.graphify.etl", p["id"]
    assert p["version"] == "1.0", p["version"]
    assert p["status"] == "draft", p["status"]
    assert p["governance"].get("hitl_required") is False, p["governance"]
    assert p["governance"].get("max_retry") == 1, p["governance"]
    assert p["governance"].get("oracle") == "evidence_seed_readiness", p["governance"]
    assert p["governance"].get("oracle_threshold") == 0.0, p["governance"]
    # kind=single → tool dispatch 가능해야 함 (dispatch._exec_workflow)
    assert p["tool"], "kind=single 인데 tool 미복원 → step_aborted(missing_tool_field)"

    m = workflow_meta.read_meta(wf)
    assert m["kind"] == "single" and m["category"] == "evidence"
    assert m["tool"] == "skb-evidence"
    assert m["governance"].get("max_retry") == 1


# ── 2. 구조 검증 위임 (MSO 부재 시 skip) ──────────────────────────────────────
@pytest.mark.skipif(
    not (_MSO_SCRIPTS / "wf_node.py").exists(),
    reason="MSO mso-workflow-design 부재 (단독 MSM 클론) — 구조검증 위임 skip",
)
@pytest.mark.parametrize("wf", _workflow_yamls(), ids=lambda p: p.name)
def test_workflow_conforms_to_mso_structure(wf):
    """각 MSM workflow 가 MSO wf_node(schema) + wf_to_ttl(SHACL/DAG) 를 통과해야 한다.

    실패 = MSO 구조 스키마가 바뀌어 MSM workflow 가 더는 정합하지 않음.
    """
    for script in ("wf_node.py", "wf_to_ttl.py"):
        sp = _MSO_SCRIPTS / script
        if not sp.exists():
            continue
        r = subprocess.run(
            [sys.executable, str(sp), "validate", str(wf)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, (
            f"MSO {script} 구조 검증 실패: {wf.name}\n{r.stdout}\n{r.stderr}"
        )
