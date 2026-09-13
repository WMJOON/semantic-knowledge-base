from __future__ import annotations

import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPOSITORY = SKILL.parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

import analyze  # noqa: E402
import scan  # noqa: E402
from ttl_state import ontology_state  # noqa: E402


def fixture_target(tmp_path: Path) -> Path:
    source = REPOSITORY / "skills/skb-ontology/tests/fixtures/ttl_demo"
    shutil.copytree(source, tmp_path, dirs_exist_ok=True)
    (tmp_path / "canonical_root_hub.yaml").write_text(
        "version: '1.1'\nlocked: true\ndomains: []\n",
        encoding="utf-8",
    )
    return tmp_path


def test_scan_and_analyze_consume_canonical_turtle(tmp_path):
    target = fixture_target(tmp_path)
    state = ontology_state(target, "demo")
    assert state["failures"] == []
    assert state["counts"]["classes"] == 2
    plan = scan.build_plan(target, "demo", "all", "test")
    assert plan["findings"]["drift"] == []
    report = analyze.build_report(target, "demo", state)
    assert "asserted Turtle files: 1" in report
    assert "classes: 2" in report


def test_dangling_turtle_link_becomes_hitl_finding(tmp_path):
    target = fixture_target(tmp_path)
    path = target / "ontology/system/semantic/demo/demo.ttl"
    path.write_text(
        path.read_text("utf-8") + "\n<https://example.org/kb#alice> <https://example.org/kb#memberOf> <https://example.org/kb#missing> .\n",
        encoding="utf-8",
    )
    plan = scan.build_plan(target, "demo", "drift", "test")
    assert any("dangling object-property target" in item["detail"] for item in plan["findings"]["drift"])
    assert plan["auto_fixes"] == []
    assert plan["hitl_required"]
