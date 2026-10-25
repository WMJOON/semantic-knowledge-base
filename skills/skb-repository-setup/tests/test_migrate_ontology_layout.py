import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import migrate_ontology_layout as M  # noqa: E402

SKILLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS / "skb-semantic-search" / "scripts"))
import skb_layout  # noqa: E402


def legacy_kb(root: Path) -> Path:
    (root / "ontology/system/semantic/demo").mkdir(parents=True)
    (root / "ontology/system/semantic/demo/demo.ttl").write_text(
        "# source: ontology/system/semantic/demo/demo.shapes.ttl\n", encoding="utf-8")
    (root / "ontology/system/semantic/demo/demo.shapes.ttl").write_text("", encoding="utf-8")
    (root / "ontology/system/kinetic").mkdir(parents=True)
    (root / "ontology/system/kinetic/demo.ttl").write_text("", encoding="utf-8")
    (root / "ontology/system/dynamic").mkdir(parents=True)
    (root / "ontology/system/dynamic/demo.ttl").write_text("", encoding="utf-8")
    (root / "canonical_root_hub.yaml").write_text(
        "version: '1.1'\nscan:\n  include: \"ontology/system/semantic/**/*.ttl\"\n", encoding="utf-8")
    (root / "agent-context/index").mkdir(parents=True)
    (root / "agent-context/index/index.yaml").write_text(
        "subdirs:\n  - path: ontology/system/kinetic/\n", encoding="utf-8")
    (root / "evidence/md").mkdir(parents=True)
    (root / "evidence/md/note.md").write_text("ontology/system/semantic/ 를 설명하는 원문", encoding="utf-8")
    return root


def test_dry_run_changes_nothing(tmp_path):
    kb = legacy_kb(tmp_path)
    before = sorted(str(p.relative_to(kb)) for p in kb.rglob("*"))
    rep = M.run(kb, apply=False)
    assert rep["conflicts"] == []
    assert any("ontology/system/semantic -> ontology/semantic" in m for m in rep["moves"])
    assert rep["leftover"] == []  # 옮겨질 파일은 남음으로 세지 않는다
    assert sorted(str(p.relative_to(kb)) for p in kb.rglob("*")) == before


def test_apply_moves_and_rewrites_metadata_but_not_evidence(tmp_path):
    kb = legacy_kb(tmp_path)
    rep = M.run(kb, apply=True)
    assert rep["conflicts"] == []
    assert (kb / "ontology/semantic/demo/demo.ttl").exists()
    assert (kb / "ontology/kinetic/demo.ttl").exists() and (kb / "ontology/dynamic/demo.ttl").exists()
    assert not (kb / "ontology/system").exists()
    hub = (kb / "canonical_root_hub.yaml").read_text(encoding="utf-8")
    assert "semantic_dir: ontology/semantic" in hub and "ontology/system" not in hub
    assert "ontology/kinetic/" in (kb / "agent-context/index/index.yaml").read_text(encoding="utf-8")
    assert "ontology/semantic/demo/demo.shapes.ttl" in (kb / "ontology/semantic/demo/demo.ttl").read_text(encoding="utf-8")
    assert "ontology/system/semantic" in (kb / "evidence/md/note.md").read_text(encoding="utf-8")


def test_apply_is_idempotent(tmp_path):
    kb = legacy_kb(tmp_path)
    M.run(kb, apply=True)
    snapshot = sorted((str(p.relative_to(kb)), p.read_bytes() if p.is_file() else None) for p in kb.rglob("*"))
    rep = M.run(kb, apply=True)
    assert rep["moves"] == [] and rep["text_files"] == []
    assert sorted((str(p.relative_to(kb)), p.read_bytes() if p.is_file() else None) for p in kb.rglob("*")) == snapshot


def test_conflict_stops_without_touching_anything(tmp_path):
    kb = legacy_kb(tmp_path)
    (kb / "ontology/semantic/other").mkdir(parents=True)
    (kb / "ontology/semantic").exists()
    before = sorted(str(p.relative_to(kb)) for p in kb.rglob("*"))
    (kb / "ontology/kinetic").mkdir(parents=True)
    (kb / "ontology/kinetic/other.ttl").write_text("", encoding="utf-8")  # 내용이 있는 새 경로 -> kinetic 충돌
    rep = M.run(kb, apply=True)
    assert rep["conflicts"]
    assert (kb / "ontology/system/kinetic/demo.ttl").exists()
    assert sorted(str(p.relative_to(kb)) for p in kb.rglob("*")) == sorted(
        before + ["ontology/kinetic", "ontology/kinetic/other.ttl"])


def test_empty_new_directory_is_not_a_conflict(tmp_path):
    kb = legacy_kb(tmp_path)
    (kb / "ontology/kinetic").mkdir(parents=True)  # apply_init 이 만든 빈 새 경로
    rep = M.run(kb, apply=True)
    assert rep["conflicts"] == []
    assert (kb / "ontology/kinetic/demo.ttl").exists()
    assert not (kb / "ontology/system/kinetic").exists()


def test_readers_find_semantic_dir_before_and_after(tmp_path):
    kb = legacy_kb(tmp_path / "before")
    assert skb_layout.semantic_dir(kb) == kb.resolve() / "ontology/system/semantic"  # 옛 KB 는 대체 경로로 읽힌다
    M.run(kb, apply=True)
    assert skb_layout.semantic_dir(kb) == kb.resolve() / "ontology/semantic"
