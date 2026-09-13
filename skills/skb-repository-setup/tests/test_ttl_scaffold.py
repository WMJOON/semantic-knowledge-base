from __future__ import annotations

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPOSITORY = SKILL.parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(REPOSITORY / "skills" / "skb-ontology" / "scripts"))

import apply_init  # noqa: E402
from ttl_validate import validate_target  # noqa: E402


def test_init_creates_valid_turtle_without_ontology_jsonl(tmp_path):
    rc = apply_init.main([
        "--target", str(tmp_path),
        "--name", "Demo KB",
        "--domain", "demo",
        "--yes",
    ])
    assert rc == 0
    canonical = tmp_path / "ontology/system/semantic/demo/demo.ttl"
    assert canonical.exists()
    assert not list((tmp_path / "ontology").rglob("*.jsonl"))
    _, _, failures = validate_target(tmp_path, "demo")
    assert failures == []
