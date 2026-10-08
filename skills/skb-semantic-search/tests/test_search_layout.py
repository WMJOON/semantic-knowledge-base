import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ss_common as C  # noqa: E402


def test_declared_layout_drives_files_and_fingerprint(tmp_path):
    (tmp_path / "canonical_root_hub.yaml").write_text(
        "layout:\n  semantic_dir: ontology/semantic\n  seeds_path: evidence/catalog/seeds.jsonl\n", encoding="utf-8")
    d = tmp_path / "ontology" / "semantic" / "x"
    d.mkdir(parents=True)
    (d / "x.ttl").write_text("a", encoding="utf-8")
    seeds = tmp_path / "evidence" / "catalog" / "seeds.jsonl"
    seeds.parent.mkdir(parents=True)
    seeds.write_text("{}\n", encoding="utf-8")
    assert [p.name for p in C.semantic_ttl_files(tmp_path)] == ["x.ttl"]
    before = C.source_fingerprint(tmp_path, "evidence")
    seeds.write_text("{}\n{}\n", encoding="utf-8")
    assert C.source_fingerprint(tmp_path, "evidence") != before
