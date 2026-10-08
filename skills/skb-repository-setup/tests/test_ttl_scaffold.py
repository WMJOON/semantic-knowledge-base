from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
REPOSITORY = SKILL.parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(REPOSITORY / "skills" / "skb-ontology" / "scripts"))

import apply_init  # noqa: E402
from ttl_validate import validate_target  # noqa: E402


@pytest.mark.parametrize("layout,canonical", [
    ("b1", "ontology/semantic/demo/demo.ttl"),
    ("legacy", "ontology/system/semantic/demo/demo.ttl"),
])
def test_init_creates_valid_turtle_without_ontology_jsonl(tmp_path, layout, canonical):
    rc = apply_init.main([
        "--target", str(tmp_path),
        "--name", "Demo KB",
        "--domain", "demo",
        "--layout", layout,
        "--yes",
    ])
    assert rc == 0
    assert (tmp_path / canonical).exists()
    assert not list((tmp_path / "ontology").rglob("*.jsonl"))
    _, _, failures = validate_target(tmp_path, "demo")
    assert failures == []


def test_default_layout_is_b1(tmp_path):
    assert apply_init.main(["--target", str(tmp_path), "--name", "Demo", "--domain", "demo", "--yes"]) == 0
    assert (tmp_path / "ontology/semantic/demo/demo.ttl").exists()
    assert not (tmp_path / "ontology/system/semantic").exists()
