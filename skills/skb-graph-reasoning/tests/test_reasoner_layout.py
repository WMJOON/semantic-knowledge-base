import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import reasoner as R  # noqa: E402
import skb_layout  # noqa: E402


def test_default_semantic_root(tmp_path):
    assert R.semantic_root(tmp_path) == tmp_path.resolve() / "ontology" / "system" / "semantic"


def test_declared_semantic_root_and_seeds(tmp_path):
    (tmp_path / "canonical_root_hub.yaml").write_text(
        "layout:\n  semantic_dir: ontology/semantic\n  seeds_path: evidence/catalog/seeds.jsonl\n", encoding="utf-8")
    d = tmp_path / "ontology" / "semantic" / "x"
    d.mkdir(parents=True)
    (d / "x.ttl").write_text("", encoding="utf-8")
    assert R.semantic_root(tmp_path) == tmp_path.resolve() / "ontology" / "semantic"
    assert [p.name for p in R.asserted_files(tmp_path)] == ["x.ttl"]
    assert skb_layout.seeds_path(tmp_path) == tmp_path.resolve() / "evidence" / "catalog" / "seeds.jsonl"
