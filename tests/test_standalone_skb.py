"""skb-* 스킬만 따로 떼어 쓸 수 있는지 시험한다 (msm-* 스킬, MSO, ~/.skill-modules, 사용자 홈의 스킬 링크 없이).

skills/skb-* 를 임시 디렉토리로 복사하고(.venv 제외), HOME 과 환경 변수를 비운 채 각 스킬의 CLI 와 하네스를 실행한다.
인터프리터는 rdflib·pyshacl·owlrl 이 설치된 현재 python 이다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
VENV_PY = Path(sys.executable)  # rdflib, pyshacl, owlrl 이 설치된 현재 인터프리터


WORKFLOW_YAML = """\
module:
  name: KB Validation
  id: validation
  version: "1.0"
x_msm:
  category: maintain
  kind: single
  mode: validate-only
  tool: skb-ontology
  governance:
    hitl_required: false
    max_retry: 1
    oracle: ontology_readiness
    oracle_threshold: 0.85
"""


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory):
    root = tmp_path_factory.mktemp("standalone")
    skills = root / "skills"
    skills.mkdir()
    for d in sorted(SKILLS.glob("skb-*")):
        shutil.copytree(d, skills / d.name, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "node_modules"))
    kb = root / "kb"
    shutil.copytree(SKILLS / "skb-ontology/tests/fixtures/ttl_demo", kb)
    (kb / "canonical_root_hub.yaml").write_text("version: '1.1'\nlocked: true\ndomains: []\n", encoding="utf-8")
    wf = kb / "agent-context/workflow/maintain"
    wf.mkdir(parents=True)
    (wf / "validation.yaml").write_text(WORKFLOW_YAML, encoding="utf-8")
    home = root / "home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "PYTHON": str(VENV_PY),
           "SKB_GRAPH_REASONING_PYTHON": str(VENV_PY), "LANG": "en_US.UTF-8"}
    return {"root": root, "skills": skills, "kb": kb, "env": env}


def run(sb, *cmd, **kw):
    return subprocess.run([str(c) for c in cmd], env=sb["env"], capture_output=True, text=True, cwd=sb["root"], **kw)


def test_sandbox_has_no_msm_or_mso_dependencies(sandbox):
    assert not any(k.startswith(("MSM_", "MSO_", "SKB_SKILL_")) for k in sandbox["env"])
    assert not (Path(sandbox["env"]["HOME"]) / ".skill-modules").exists()
    assert not list(sandbox["skills"].glob("msm-*")) and not list(sandbox["skills"].glob("mso-*"))
    assert not (sandbox["skills"] / "skb-maintain").exists()


def test_ontology_validate_stats_orphans(sandbox):
    cli = sandbox["skills"] / "skb-ontology/scripts/skb-ontology"
    kb = sandbox["kb"]
    assert run(sandbox, cli, "validate", "--target", kb, "--domain", "demo").returncode == 0
    r = run(sandbox, cli, "stats", "--target", kb, "--domain", "demo", "--json")
    assert r.returncode == 0 and json.loads(r.stdout)["counts"]["classes"] == 2
    assert run(sandbox, cli, "orphans", "--target", kb, "--domain", "demo", "--json").returncode == 0


def test_graph_reasoning_reason_apply_and_status(sandbox):
    cli = sandbox["skills"] / "skb-graph-reasoning/scripts/skb-graph-reasoning"
    kb = sandbox["kb"]
    r = run(sandbox, cli, "reason", "--target", kb, "--domain", "demo", "--apply")
    assert r.returncode == 0, r.stderr
    assert (kb / "ontology/system/semantic/demo/demo.inferred.ttl").exists()
    assert run(sandbox, cli, "status", "--target", kb, "--domain", "demo").returncode == 0
    assert run(sandbox, cli, "check", "--target", kb).returncode == 0


def test_ontology_reason_delegates_to_sibling_reasoner(sandbox):
    cli = sandbox["skills"] / "skb-ontology/scripts/skb-ontology"
    r = run(sandbox, cli, "reason", "--target", sandbox["kb"], "--domain", "demo")
    assert r.returncode == 0 and "skb-graph-reasoning" in r.stderr


def test_evidence_verify_with_stdlib_only(sandbox, tmp_path):
    kb = tmp_path / "ev"
    (kb / "evidence/md").mkdir(parents=True)
    import hashlib
    text = "첫 문단입니다."
    note = f"<!-- generated -->\n---\nid: evidence:seed:a_0000\nuri: https://e.com/a\n---\n\n# T\n\n> Source: https://e.com/a\n\n{text}\n"
    (kb / "evidence/md/a_0000.md").write_text(note, encoding="utf-8")
    seed = {"id": "evidence:seed:a_0000", "uri": "https://e.com/a", "md_path": "evidence/md/a_0000.md",
            "content_hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest()}
    (kb / "evidence/seeds.jsonl").write_text(json.dumps(seed) + "\n", encoding="utf-8")
    r = run(sandbox, sandbox["skills"] / "skb-evidence/scripts/skb-evidence", "verify", "--target", kb, "--orphans", "--strict")
    assert r.returncode == 0, r.stdout + r.stderr


def test_harness_workflow_finds_skill_and_oracle_among_siblings(sandbox):
    kb = sandbox["kb"]
    r = run(sandbox, sandbox["skills"] / "skb-harness/runtime/run.sh", "--workflow", "agent-context/workflow/maintain/validation.yaml",
            "--tier", "L0", "--mode", "validate-only", "--target", kb)
    events = []
    for f in (kb / "harness/trajectory").glob("run-*.jsonl"):
        events += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    kinds = [e.get("event_type") for e in events]
    assert "step_aborted" not in kinds, f"skill 을 찾지 못했다: {r.stderr[-400:]}"
    ev = [e for e in events if e.get("event_type") == "oracle_evaluation"]
    assert ev, f"oracle 이벤트가 없다: {kinds}"
    assert ev[0]["oracle"] == "ontology_readiness"
    assert "skipped" not in (ev[0].get("details") or {}), "oracle 이 vacuous PASS 로 처리됐다"
    assert isinstance(ev[0]["score"], float)
