"""layout.py — canonical_root_hub.yaml 의 layout: 섹션 해석 시험."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("skb_layout_under_test", SCRIPTS / "layout.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_default_without_hub(tmp_path):
    lay = _load().resolve_layout(tmp_path)
    assert lay["semantic_dir"] == tmp_path.resolve() / "ontology" / "system" / "semantic"


def test_default_without_layout_section(tmp_path):
    (tmp_path / "canonical_root_hub.yaml").write_text("domains: {}\n", encoding="utf-8")
    lay = _load().resolve_layout(tmp_path)
    assert lay["semantic_dir"] == tmp_path.resolve() / "ontology" / "system" / "semantic"


def test_declared_relative_and_absolute(tmp_path):
    abs_dir = tmp_path / "elsewhere"
    (tmp_path / "canonical_root_hub.yaml").write_text(
        f"layout:\n  semantic_dir: ontology/semantic\n  table_dir: {abs_dir}\n", encoding="utf-8"
    )
    lay = _load().resolve_layout(tmp_path)
    assert lay["semantic_dir"] == tmp_path.resolve() / "ontology" / "semantic"
    assert lay["table_dir"] == abs_dir
    assert lay["explain_dir"] == tmp_path.resolve() / "ontology" / "explain"


def test_invalid_yaml_warns_and_defaults(tmp_path, capsys):
    (tmp_path / "canonical_root_hub.yaml").write_text("layout: [unclosed\n", encoding="utf-8")
    lay = _load().resolve_layout(tmp_path)
    assert lay["semantic_dir"] == tmp_path.resolve() / "ontology" / "system" / "semantic"
    assert "파싱 실패" in capsys.readouterr().err


def test_without_pyyaml_still_honors_layout(tmp_path):
    (tmp_path / "canonical_root_hub.yaml").write_text(
        "domains: {}\nlayout:\n  semantic_dir: ontology/semantic  # 도메인별 TTL\n", encoding="utf-8"
    )
    mod = _load()
    mod.yaml = None
    lay = mod.resolve_layout(tmp_path)
    assert lay["semantic_dir"] == tmp_path.resolve() / "ontology" / "semantic"
