from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import oracle_runner as R  # noqa: E402


def _oracle(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_no_oracle_name_is_benign(tmp_path):
    r = R.run_oracle(tmp_path, None, {})
    assert r["score"] == 1.0 and r["details"] == {"skipped": "no_oracle"}


def test_missing_oracle_is_flagged_as_vacuous_with_search_paths(tmp_path):
    r = R.run_oracle(tmp_path / "kb", "nope", {}, skills_dir=tmp_path / "skills")
    assert r["passed"] is True and r["score"] == 1.0
    assert r["details"]["skipped"] == "function_not_found"
    assert "vacuous" in r["details"]["warning"]
    assert any(p.endswith("harness/oracle/nope.py") for p in r["details"]["searched"])


def test_oracle_in_sibling_skill_is_discovered(tmp_path):
    skills = tmp_path / "skills"
    _oracle(skills / "skb-demo" / "oracle" / "demo_readiness.py", "def evaluate(target):\n    return {'score': 0.5, 'extra': 1}\n")
    r = R.run_oracle(tmp_path / "kb", "demo_readiness", {"run_id": "x"}, skills_dir=skills)
    assert r["score"] == 0.5
    assert r["passed"] is False
    assert r["details"] == {"extra": 1}  # 규약의 details 가 없으면 나머지 키가 details


def test_loader_passes_only_accepted_arguments(tmp_path):
    skills = tmp_path / "skills"
    _oracle(skills / "a" / "oracle" / "o1.py", "def evaluate(target, run_context=None):\n    return {'score': 1.0, 'passed': True, 'details': {'rid': run_context['run_id']}}\n")
    _oracle(skills / "a" / "oracle" / "o2.py", "def evaluate(**kw):\n    return {'score': 1.0, 'passed': True, 'details': {'keys': sorted(kw)}}\n")
    assert R.run_oracle(tmp_path, "o1", {"run_id": "r1"}, skills_dir=skills)["details"] == {"rid": "r1"}
    assert R.run_oracle(tmp_path, "o2", {"run_id": "r1"}, skills_dir=skills)["details"] == {"keys": ["run_context", "target"]}


def test_repo_oracle_overrides_skill_oracle(tmp_path):
    kb, skills = tmp_path / "kb", tmp_path / "skills"
    _oracle(skills / "a" / "oracle" / "o.py", "def evaluate(target):\n    return {'score': 0.1, 'passed': False}\n")
    _oracle(kb / "harness" / "oracle" / "o.py", "def evaluate(target):\n    return {'score': 0.9, 'passed': True}\n")
    assert R.run_oracle(kb, "o", {}, skills_dir=skills)["score"] == 0.9


def test_oracle_exception_scores_zero(tmp_path):
    skills = tmp_path / "skills"
    _oracle(skills / "a" / "oracle" / "boom.py", "def evaluate(target):\n    raise RuntimeError('x')\n")
    r = R.run_oracle(tmp_path, "boom", {}, skills_dir=skills)
    assert r["score"] == 0.0 and r["passed"] is False and r["details"]["error"] == "x"


def test_real_skill_oracles_are_discoverable():
    skills = Path(__file__).resolve().parents[2]
    found = {p.stem for p in skills.glob("*/oracle/*.py")}
    assert {"ontology_readiness", "evidence_seed_readiness"} <= found
