import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ss_hybrid as H
import ss_sparql as S


def test_tokenize_korean_bigrams_and_latin_words():
    toks = H.tokenize("매출증가 Revenue-2026")
    assert "매출증가" in toks and "매출" in toks and "출증" in toks
    assert "revenue" in toks and "2026" in toks


def test_bm25_prefers_label_match_over_definition_match():
    docs = {
        "label_hit": H.bm25_tokens({"label": "revenue", "alt": [], "hidden": [], "note": ""}),
        "note_hit": H.bm25_tokens({"label": "other", "alt": [], "hidden": [], "note": "revenue"}),
    }
    assert H.Bm25(docs).rank("revenue")[0] == "label_hit"


def test_bm25_respects_candidate_ids_and_returns_nothing_without_match():
    docs = {"a": H.tokenize("alpha"), "b": H.tokenize("alpha beta")}
    assert H.Bm25(docs).rank("alpha", ids=["b"]) == ["b"]
    assert H.Bm25(docs).rank("gamma") == []


def test_rrf_fuse_rewards_items_present_in_both_rankings():
    fused = H.rrf_fuse([["x", "y", "z"], ["y", "w"]])
    assert fused[0][0] == "y"


def test_concept_match_mirrors_default_deprecated_and_scheme_rules():
    assert H.concept_match({"status": "accepted"})
    assert H.concept_match({"status": ""})
    assert not H.concept_match({"status": "deprecated"})
    assert H.concept_match({"status": "deprecated"}, include_deprecated=True)
    assert not H.concept_match({"status": "draft", "scheme": "A"}, statuses=["accepted"])
    assert not H.concept_match({"status": "accepted", "scheme": "A"}, scheme="B")


def test_tbox_doc_requires_label_and_carries_domain_range():
    assert H.tbox_doc({"iri": "https://x/c", "pref_en": [], "pref_ko": []}) is None
    text, fields = H.tbox_doc({"iri": "https://x/p", "tkind": "property", "pref_en": ["owns"], "pref_ko": [],
                               "alt": ["has"], "note": "소유", "domain": ["https://x/A"], "range": ["https://x/B"], "super": []})
    assert "owns" in text and "has" in text and "소유" in text
    assert fields["domain"] == "https://x/A" and fields["range"] == "https://x/B" and fields["tkind"] == "property"


def _tbox_rows():
    return {
        "https://x/A": {"iri": "https://x/A", "tkind": "class", "pref_en": ["A"], "super": ["https://x/Top"], "domain": [], "range": []},
        "https://x/Top": {"iri": "https://x/Top", "tkind": "class", "pref_en": ["Top"], "super": [], "domain": [], "range": []},
        "https://x/p": {"iri": "https://x/p", "tkind": "property", "pref_en": ["p"], "domain": ["https://x/A"], "range": ["https://x/B"], "super": []},
        "https://x/B": {"iri": "https://x/B", "tkind": "class", "pref_en": ["B"], "super": [], "domain": [], "range": []},
    }


def test_expand_class_adds_its_properties_and_superclass():
    items = H.expand_tbox([{"iri": "https://x/A"}], _tbox_rows(), max_add=10)
    got = {(i["iri"], i["reason"]) for i in items}
    assert ("https://x/A", "hit") in got
    assert ("https://x/p", "property-of-class") in got
    assert ("https://x/Top", "superclass") in got


def test_expand_property_adds_domain_and_range_after_hits():
    items = H.expand_tbox([{"iri": "https://x/p"}], _tbox_rows(), max_add=10)
    assert items[0]["iri"] == "https://x/p" and items[0]["reason"] == "hit"
    reasons = {i["iri"]: i["reason"] for i in items[1:]}
    assert reasons == {"https://x/A": "domain-of", "https://x/B": "range-of"}


def test_expand_respects_max_add():
    items = H.expand_tbox([{"iri": "https://x/A"}], _tbox_rows(), max_add=1)
    assert len([i for i in items if i["reason"] != "hit"]) == 1


# ---- SPARQL 템플릿
def test_bundled_templates_are_valid_and_read_only():
    tpls = S.load_templates()
    assert len(tpls) >= 8
    for t in tpls:
        assert S.validate_template(t) == [], t["id"]


def test_validate_flags_undeclared_and_unused_slots_and_writes():
    bad = {"id": "x", "questions": ["q"], "description": "d", "slots": {"A": "class", "Z": "class"},
           "sparql": "SELECT ?s WHERE { ?s ?p <<A>> . <<B>> ?p ?s }"}
    errs = S.validate_template(bad)
    assert any("선언되지 않은" in e and "B" in e for e in errs)
    assert any("쓰이지 않는" in e and "Z" in e for e in errs)
    write = dict(bad, slots={"A": "class"}, sparql="INSERT DATA { <urn:a> <urn:b> <<A>> }")
    assert any("읽기 전용" in e or "쓰기" in e for e in S.validate_template(write))


def test_search_templates_finds_by_question_text():
    tpls = S.load_templates()
    top = S.search_templates("하위 클래스", tpls, k=1)
    assert top and top[0]["id"] == "subclasses-of"


def test_fill_replaces_slots_with_iris_only():
    t = {"sparql": "SELECT ?s WHERE { ?s <<PROP>> <<CLS>> }", "slots": {"PROP": "property", "CLS": "class"}}
    q = S.fill(t, {"PROP": "https://x/p", "CLS": "urn:x:c"})
    assert q == "SELECT ?s WHERE { ?s <https://x/p> <urn:x:c> }"


def test_fill_rejects_missing_slot_and_non_iri_value():
    t = {"sparql": "SELECT ?s WHERE { ?s <<P>> ?o }", "slots": {"P": "property"}}
    with pytest.raises(ValueError):
        S.fill(t, {})
    with pytest.raises(ValueError):
        S.fill(t, {"P": "not an iri"})


def test_assert_read_only_blocks_updates():
    with pytest.raises(ValueError):
        S.assert_read_only("DELETE WHERE { ?s ?p ?o }")
    S.assert_read_only("SELECT ?s WHERE { ?s ?p ?o }")


def test_resolve_tbox_returns_top_iri_and_candidates_by_kind():
    rows = [{"iri": "https://x/Cross", "tkind": "class", "pref_en": ["Cross-Border Commerce"], "alt": ["해외직구"]},
            {"iri": "https://x/p", "tkind": "property", "pref_en": ["Cross-Border Commerce link"]}]
    iri, cands = S.resolve_tbox("해외직구", rows, "class")
    assert iri == "https://x/Cross" and cands == ["https://x/Cross"]
    with pytest.raises(ValueError):
        S.resolve_tbox("없는말", rows, "class")


def test_run_select_on_small_graph_and_load_graph_skips_bad_files(tmp_path):
    rdflib = pytest.importorskip("rdflib")
    ttl_dir = tmp_path / "ontology" / "system" / "semantic" / "x"
    ttl_dir.mkdir(parents=True)
    (ttl_dir / "ok.ttl").write_text(
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
        "<https://x/A> a <http://www.w3.org/2002/07/owl#Class> .\n"
        "<https://x/i1> a <https://x/A> .\n", encoding="utf-8")
    (ttl_dir / "bad.ttl").write_text("this is not turtle {{{", encoding="utf-8")
    g, failed = S.load_graph(tmp_path)
    assert any("bad.ttl" in f for f in failed)
    tpl = next(t for t in S.load_templates() if t["id"] == "instances-of-class")
    q = S.fill(tpl, {"CLASS": "https://x/A"})
    res = S.run_select(g, q)
    assert res["vars"] == ["s", "label"]
    assert res["rows"][0][0] == "https://x/i1"
