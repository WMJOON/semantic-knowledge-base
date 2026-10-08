from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL / "oracle"))

import ontology_readiness  # noqa: E402
import ttl_report  # noqa: E402
from ttl_state import ontology_state  # noqa: E402


def fixture_target(tmp_path: Path) -> Path:
    shutil.copytree(SKILL / "tests/fixtures/ttl_demo", tmp_path, dirs_exist_ok=True)
    (tmp_path / "canonical_root_hub.yaml").write_text("version: '1.1'\nlocked: true\ndomains: []\n", encoding="utf-8")
    return tmp_path


def test_state_reads_canonical_turtle(tmp_path):
    state = ontology_state(fixture_target(tmp_path), "demo")
    assert state["failures"] == []
    assert state["counts"]["classes"] == 2


def test_stats_text_reports_counts(tmp_path):
    target = fixture_target(tmp_path)
    text = ttl_report.stats_text(target, "demo", ontology_state(target, "demo"))
    assert "asserted Turtle files: 1" in text and "classes: 2" in text


def test_stats_cli_json_and_exit_code(tmp_path, capsys):
    target = fixture_target(tmp_path)
    assert ttl_report.main(["stats", "--target", str(target), "--domain", "demo", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["classes"] == 2


def test_orphans_cli_lists_unconnected_accepted_terms(tmp_path, capsys):
    target = fixture_target(tmp_path)
    assert ttl_report.main(["orphans", "--target", str(target), "--domain", "demo", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["count"] == len(out["orphans"])


def test_dangling_link_makes_report_exit_nonzero(tmp_path):
    target = fixture_target(tmp_path)
    path = target / "ontology/system/semantic/demo/demo.ttl"
    path.write_text(path.read_text("utf-8") + "\n<https://example.org/kb#alice> <https://example.org/kb#memberOf> <https://example.org/kb#missing> .\n", encoding="utf-8")
    assert ttl_report.main(["stats", "--target", str(target), "--domain", "demo"]) == 1
    assert any("dangling object-property target" in f for f in ontology_state(target, "demo")["failures"])


def test_readiness_oracle_follows_harness_contract(tmp_path):
    target = fixture_target(tmp_path)
    result = ontology_readiness.evaluate(target=target, run_context={"run_id": "t"}, domain="demo")
    assert set(result) >= {"score", "passed", "details"}
    assert 0.0 <= result["score"] <= 1.0
    assert result["details"]["metrics"]["ttl_validation_failures"] == 0
    assert result["details"]["metrics"]["canonical_hub_locked"] is True
