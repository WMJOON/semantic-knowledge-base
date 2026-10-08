"""skb init 이 만든 저장소를 공개 도구가 그대로 읽고 돌리는지 확인한다 (스캐폴드 ↔ 도구 정합).

init 만 시험하면 템플릿이 도구 이름·경로와 어긋나도 모른다. 여기서는 init 산출물에 실제 스킬 CLI·하네스·lint 를 돌린다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
SKILLS = SKILL.parent
APPLY = SKILL / "scripts" / "apply_init.py"
LINT = SKILL / "harness" / "tiers" / "L0_static" / "validate_workflows.py"
LAYOUT_VALIDATOR = SKILL / "harness" / "tiers" / "L0_static" / "validate_repository_setup.py"
HARNESS = SKILLS / "skb-harness" / "runtime" / "run.sh"
ENV = {**os.environ, "PYTHON": sys.executable}


def sh(*cmd, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=ENV, **kw)


@pytest.fixture(scope="module")
def kb(tmp_path_factory):
    root = tmp_path_factory.mktemp("kb") / "demo"
    r = sh(sys.executable, APPLY, "--target", root, "--name", "demo", "--domain", "demo", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    return root


def test_layout_section_declares_the_paths(kb):
    hub = (kb / "canonical_root_hub.yaml").read_text(encoding="utf-8")
    for key in ("semantic_dir: ontology/semantic", "seeds_path: evidence/catalog/seeds.jsonl",
                "raw_dir: evidence/artifact/raw", "evidence_md_dir: evidence/chunk"):
        assert key in hub
    for d in ("ontology/semantic/demo", "evidence/artifact/raw", "evidence/chunk", "evidence/catalog"):
        assert (kb / d).is_dir()
    assert not (kb / "ontology/system/semantic").exists() and not (kb / "evidence/raw").exists()


def test_artifact_registry_modules_are_declared_in_index(kb):
    """레지스트리의 wf:inModule 은 agent-context/index/index.yaml 의 module id 여야 한다(MSO 교차층 검증과 같은 규칙)."""
    import re

    import yaml

    modules = {m["id"]: m["path"] for m in yaml.safe_load((kb / "agent-context/index/index.yaml").read_text(encoding="utf-8"))["modules"]}
    text = (kb / "agent-context/index/artifacts.abox.ttl").read_text(encoding="utf-8")
    used = set(re.findall(r'wf:inModule\s+"([^"]+)"', text))
    assert used and used <= set(modules), used - set(modules)
    # 각 규약의 directoryTemplate 은 자기 모듈 경로 아래에 있어야 한다
    for block in re.findall(r'(art:\w+ a wf:RegisteredArtifact.*?)(?=\nart:\w+ a wf:RegisteredArtifact|\Z)', text, re.S):
        mod = re.search(r'wf:inModule\s+"([^"]+)"', block).group(1)
        conv = re.search(r'wf:hasConvention\s+(art:\w+)', block).group(1)
        d = re.search(re.escape(conv) + r' a wf:ArtifactConvention.*?wf:directoryTemplate\s+"([^"]+)"', text, re.S).group(1)
        assert d.startswith(modules[mod]), (conv, d, modules[mod])


def test_required_dirs_validator_passes(kb):
    r = sh(sys.executable, LAYOUT_VALIDATOR, "--target", kb)
    assert r.returncode == 0, r.stderr


def test_published_tools_read_the_layout(kb):
    assert sh(SKILLS / "skb-ontology/scripts/skb-ontology", "validate", "--target", kb, "--domain", "demo").returncode == 0
    r = sh(sys.executable, SKILLS / "skb-graph-reasoning/scripts/graph_reasoning.py", "check", "--target", kb)
    assert r.returncode == 0 and "triples=1 " in r.stdout, r.stdout + r.stderr
    assert sh(SKILLS / "skb-evidence/scripts/skb-evidence", "verify", "--target", kb).returncode == 0
    r = sh(sys.executable, SKILLS / "skb-semantic-search/scripts/semantic_search.py", "status", "--target", kb)
    assert r.returncode in (0, 1), r.stderr


def test_workflows_are_ttl_and_lint_finds_no_mismatch(kb):
    wf = sorted((kb / "agent-context/workflow").rglob("*"))
    assert [p.name for p in wf if p.is_file()] == sorted([
        "workflow-evidence-collection.abox.ttl", "workflow-ontology-construction.abox.ttl",
        "workflow-search-reason.abox.ttl", "workflow-validation.abox.ttl"])
    r = sh(sys.executable, LINT, "--target", kb)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "4 ttl workflow(s)" in r.stdout


def test_lint_rejects_unknown_tool_and_oracle(kb, tmp_path):
    bad = tmp_path / "bad"
    (bad / "agent-context/workflow").mkdir(parents=True)
    ttl = (kb / "agent-context/workflow/workflow-validation.abox.ttl").read_text(encoding="utf-8")
    ttl = ttl.replace('skbx:tool "skb-ontology"', 'skbx:tool "msm-nonexistent"').replace(
        'skbx:oracle "ontology_readiness"', 'skbx:oracle "no_such_oracle"')
    (bad / "agent-context/workflow/workflow-validation.abox.ttl").write_text(ttl, encoding="utf-8")
    r = sh(sys.executable, LINT, "--target", bad)
    assert r.returncode == 1
    assert "msm-nonexistent" in r.stderr and "no_such_oracle" in r.stderr


@pytest.mark.parametrize("name", ["validation", "ontology-construction", "search-reason"])
def test_harness_runs_workflow_with_a_real_oracle(kb, name):
    for f in (kb / "harness/trajectory").glob("run-*.jsonl"):
        f.unlink()
    sh(HARNESS, "--workflow", f"agent-context/workflow/workflow-{name}.abox.ttl", "--tier", "L0",
       "--mode", "validate-only", "--target", kb)
    events = []
    for f in (kb / "harness/trajectory").glob("run-*.jsonl"):
        events += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    kinds = [e.get("event_type") for e in events]
    assert "step_aborted" not in kinds, kinds
    ev = [e for e in events if e.get("event_type") == "oracle_evaluation"]
    assert ev and isinstance(ev[0]["score"], float)
    assert "skipped" not in (ev[0].get("details") or {}), "oracle 이 vacuous PASS 로 처리됐다"
    assert ev[0]["passed"] is True


def test_gitignore_covers_private_and_derived_paths(kb):
    text = (kb / ".gitignore").read_text(encoding="utf-8")
    for pat in ("evidence/artifact/raw/**", "evidence/catalog/seeds.jsonl", "**/*.inferred.ttl",
                "embedding/", "harness/trajectory/**", "record-archive/runtime/**"):
        assert pat in text


def test_existing_gitignore_is_left_alone(tmp_path):
    root = tmp_path / "kb"
    root.mkdir()
    (root / ".gitignore").write_text("mine\n", encoding="utf-8")
    assert sh(sys.executable, APPLY, "--target", root, "--name", "k", "--domain", "d", "--yes").returncode == 0
    assert (root / ".gitignore").read_text(encoding="utf-8") == "mine\n"


def test_kb_without_layout_section_keeps_old_paths(tmp_path):
    """layout: 이 없는 KB(옛 배치)는 이전과 똑같이 ontology/system/semantic 을 읽는다."""
    root = tmp_path / "old"
    r = sh(sys.executable, APPLY, "--target", root, "--name", "old", "--domain", "demo", "--layout", "legacy", "--yes")
    assert r.returncode == 0, r.stderr
    assert "layout:" not in (root / "canonical_root_hub.yaml").read_text(encoding="utf-8")
    assert (root / "ontology/system/semantic/demo/demo.ttl").exists()
    assert sh(SKILLS / "skb-ontology/scripts/skb-ontology", "validate", "--target", root, "--domain", "demo").returncode == 0
    r = sh(sys.executable, SKILLS / "skb-graph-reasoning/scripts/graph_reasoning.py", "check", "--target", root)
    assert r.returncode == 0 and "triples=1 " in r.stdout
    assert sh(sys.executable, LINT, "--target", root).returncode == 0
    assert sh(sys.executable, LAYOUT_VALIDATOR, "--target", root).returncode == 0
