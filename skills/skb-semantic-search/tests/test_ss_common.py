import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ss_common as C


def test_sql_quote_escapes_single_quote():
    assert C.sql_quote("it's") == "'it''s'"


def test_concept_filter_default_excludes_deprecated():
    assert C.concept_filter() == "status != 'deprecated'"


def test_concept_filter_include_deprecated_has_no_clause():
    assert C.concept_filter(include_deprecated=True) is None


def test_concept_filter_statuses_override_default_and_combine_with_scheme():
    f = C.concept_filter(["accepted", "draft"], scheme="https://x/s")
    assert f == "(status = 'accepted' or status = 'draft') and scheme = 'https://x/s'"
    assert "deprecated" not in f


def test_evidence_filter():
    assert C.evidence_filter() is None
    assert C.evidence_filter(uri="https://a/b") == "uri = 'https://a/b'"
    assert C.evidence_filter(uri_contains="sec.gov") == "uri like '%sec.gov%'"
    assert C.evidence_filter(uri="u", uri_contains="v") == "uri = 'u' and uri like '%v%'"


def test_group_by_doc_keeps_best_chunk_and_counts_regardless_of_input_order():
    hits = [{"uri": "a", "sim": 0.5, "seed_id": "a1"}, {"uri": "b", "sim": 0.9, "seed_id": "b1"},
            {"uri": "a", "sim": 0.7, "seed_id": "a2"}, {"uri": "a", "sim": 0.6, "seed_id": "a3"}]
    out = C.group_by_doc(hits, k=5)
    assert [h["uri"] for h in out] == ["b", "a"]
    a = out[1]
    assert a["seed_id"] == "a2" and a["chunks_hit"] == 3 and a["sim"] == 0.7


def test_group_by_doc_limits_to_k_documents():
    hits = [{"uri": str(i), "sim": i / 10, "seed_id": str(i)} for i in range(6)]
    assert [h["uri"] for h in C.group_by_doc(hits, k=2)] == ["5", "4"]


def test_strip_frontmatter_removes_generated_comment_and_header():
    t = "<!-- msm:generated -->\n---\nid: x\nuri: y\n---\n\n# Title\nbody"
    assert C.strip_frontmatter(t) == "# Title\nbody"
    assert C.strip_frontmatter("plain body") == "plain body"


def test_concept_doc_builds_label_alt_and_note():
    row = {"iri": "i", "pref_en": ["Bond"], "pref_ko": ["채권"], "alt": ["Debt"], "scope_note": "note", "status": "accepted", "scheme": "s"}
    text, fields = C.concept_doc(row)
    assert text == "Bond / 채권 (Debt): note"
    assert fields == {"iri": "i", "label": "Bond / 채권", "status": "accepted", "scheme": "s"}
    assert C.concept_doc({"iri": "i", "pref_en": [], "pref_ko": []}) is None


def _kb(tmp_path, ttl="a"):
    sem = tmp_path / C.SEMANTIC_DIR / "d"
    sem.mkdir(parents=True)
    (sem / "x.ttl").write_text(ttl)
    (sem / "x.shapes.ttl").write_text("ignored")
    (sem / "x.inferred.ttl").write_text("ignored")
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "seeds.jsonl").write_text('{"id":"1"}\n')
    return tmp_path


def test_fingerprint_ignores_shapes_and_inferred_but_tracks_content(tmp_path):
    kb = _kb(tmp_path)
    f1 = C.source_fingerprint(kb, "concepts")
    (kb / C.SEMANTIC_DIR / "d" / "x.shapes.ttl").write_text("changed")
    assert C.source_fingerprint(kb, "concepts") == f1
    (kb / C.SEMANTIC_DIR / "d" / "x.ttl").write_text("b")
    assert C.source_fingerprint(kb, "concepts") != f1


def test_freshness_missing_fresh_and_stale(tmp_path):
    kb = _kb(tmp_path)
    sd = kb / "embedding"
    sd.mkdir()
    assert C.freshness(kb, sd, "concepts")["state"] == "missing"
    (sd / C.STORE_NAMES["concepts"]).mkdir()
    C.write_manifest_entry(sd, "concepts", {"model": C.MODEL, "dim": C.DIM, "built_at": "t", "indexed": 1, "skipped": 0,
                                            "source_fingerprint": C.source_fingerprint(kb, "concepts")})
    assert C.freshness(kb, sd, "concepts")["state"] == "fresh"
    (kb / C.SEMANTIC_DIR / "d" / "x.ttl").write_text("changed")
    r = C.freshness(kb, sd, "concepts")
    assert r["state"] == "stale" and "source changed" in r["reasons"][0]


def test_freshness_stale_when_model_changes(tmp_path):
    kb = _kb(tmp_path)
    sd = kb / "embedding"
    sd.mkdir()
    (sd / C.STORE_NAMES["evidence"]).mkdir()
    C.write_manifest_entry(sd, "evidence", {"model": "old-model", "dim": C.DIM, "source_fingerprint": C.source_fingerprint(kb, "evidence")})
    r = C.freshness(kb, sd, "evidence")
    assert r["state"] == "stale" and any("model changed" in x for x in r["reasons"])


def test_freshness_stale_when_index_is_partial(tmp_path):
    kb = _kb(tmp_path)
    sd = kb / "embedding"
    sd.mkdir()
    (sd / C.STORE_NAMES["evidence"]).mkdir()
    C.write_manifest_entry(sd, "evidence", {"model": C.MODEL, "dim": C.DIM, "limited": True,
                                            "source_fingerprint": C.source_fingerprint(kb, "evidence")})
    r = C.freshness(kb, sd, "evidence")
    assert r["state"] == "stale" and any("partial" in y for y in r["reasons"])
