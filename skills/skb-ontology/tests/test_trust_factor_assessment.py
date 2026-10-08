"""TrustFactorAssessment 회귀 테스트: 신뢰도 = 공신력 x 성실도 가 실제로 강제되고 계산되는지 확인한다.

  공신력: 발행자(사람·조직)에 붙는 요인. 평가가 없으면 모름(문서 유형의 기본값 없음).
  성실도: 문서에 붙는 요인. 평가가 없으면 문서 유형의 기본값, 그것도 없으면 모름.
  신뢰도: 저장하지 않는 파생값. 3x3 표에 따라 약한 쪽을 따르고, 하나라도 모르면 계산 불가.
SHACL 규칙과 effective_trust.rq 를 함께 본다. 실행: python -m unittest test_trust_factor_assessment -v
"""
import itertools
import unittest
from pathlib import Path

from rdflib import Graph, URIRef

import test_source_agents_shapes as SAT

HERE = Path(__file__).parent
QUERY = (SAT.D / "queries" / "effective_trust.rq").read_text(encoding="utf-8")
C = "https://skb.dev/ontology/source-agents/concept#"

PRE = SAT.PRE + """
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
"""
DOC = "<https://example.org/doc1>"
KARP = "<https://example.org/skb/person/andrej-karpathy>"
OTHER = "<https://example.org/skb/person/other-author>"
TOPICS = """
<https://skb.dev/ontology/source-agents/concept-scheme/topics-test> a skos:ConceptScheme .
concept:topic-llm a skos:Concept ; skos:inScheme <https://skb.dev/ontology/source-agents/concept-scheme/topics-test> .
concept:topic-tax a skos:Concept ; skos:inScheme <https://skb.dev/ontology/source-agents/concept-scheme/topics-test> .
"""
DOC_DATA = f"""{DOC} dcterms:type concept:source-type-paper ; dcterms:publisher {KARP} .\n"""
T1, T2, T3 = ('"2026-09-30T01:00:00Z"^^xsd:dateTime', '"2026-09-30T02:00:00Z"^^xsd:dateTime', '"2026-09-30T03:00:00Z"^^xsd:dateTime')

# 결합 규칙의 3x3 표(effective_trust.rq 머리말과 같다). 순서: 낮음 < 중 < 높음, 약한 쪽을 따른다.
TABLE = {("low", "low"): "low", ("low", "medium"): "low", ("low", "high"): "low",
         ("medium", "low"): "low", ("medium", "medium"): "medium", ("medium", "high"): "medium",
         ("high", "low"): "low", ("high", "medium"): "medium", ("high", "high"): "high"}      # (공신력, 성실도) -> 신뢰도


def asm(aid="aaaaaaaaaaaaaaaa", factor="diligence", level="low", status="accepted", at=T1, topic=None, target=None, basis=True, by=True, supersedes=None):
    tgt = target or (f"sa:assessesDocument {DOC}" if factor == "diligence" else f"sa:assessesAgent {KARP}")
    s = (f"<https://example.org/skb/trust-factor/{aid}> a sa:TrustFactorAssessment ; {tgt} ; sa:trustFactor concept:trust-factor-{factor} ; "
         f"sa:factorLevel concept:trust-level-{level} ; sa:assessmentStatus \"{status}\" ; prov:generatedAtTime {at}")
    if basis: s += " ; sa:assessmentBasis <https://example.org/evidence1>"
    if by: s += " ; sa:assessedBy <https://example.org/skb/person/reviewer>"
    if topic: s += f" ; sa:aboutTopic concept:topic-{topic}"
    if supersedes: s += f" ; sa:supersedesAssessment <https://example.org/skb/trust-factor/{supersedes}>"
    return s + " .\n"


BASE_SHACL = SAT.PA + "@prefix dcterms: <http://purl.org/dc/terms/> .\n@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n" + SAT.PERSON + SAT.ORG + SAT.claim(identity=KARP) + TOPICS + DOC_DATA


class ShaclTest(unittest.TestCase):
    def check(self, ttl, expect):
        ok, text = SAT.run(BASE_SHACL + ttl)
        self.assertFalse(ok, "위반을 놓침")
        self.assertIn(expect, text)

    def ok(self, ttl):
        ok, text = SAT.run(BASE_SHACL + ttl)
        self.assertTrue(ok, text[:900])

    def test_valid_diligence_and_authority_assessments(self):
        self.ok(asm() + asm("bbbbbbbbbbbbbbbb", factor="authority", level="high", topic="llm"))

    def test_candidate_may_lack_basis_and_reviewer(self):
        self.ok(asm(status="candidate", basis=False, by=False))

    def test_accepted_needs_basis_and_reviewer(self):
        self.check(asm(basis=False), "근거 없는 평가")
        self.check(asm(by=False), "근거 없는 평가")

    def test_exactly_one_target_and_factor_matches_target(self):
        self.check(asm(target=f"sa:assessesDocument {DOC} ; sa:assessesAgent {KARP}"), "정확히 하나")
        self.check(asm().replace(f"sa:assessesDocument {DOC} ; ", ""), "정확히 하나")
        self.check(asm(factor="authority", target=f"sa:assessesDocument {DOC}"), "요인과 대상이 어긋난다")
        self.check(asm(factor="diligence", target=f"sa:assessesAgent {KARP}"), "요인과 대상이 어긋난다")

    def test_authority_target_must_be_person_or_organization(self):
        self.check(asm(factor="authority", target="sa:assessesAgent <https://example.org/skb/agent/ghost>"), "sa:Person 또는 sa:Organization")

    def test_factor_and_level_come_from_their_schemes(self):
        self.check(asm().replace("concept:trust-factor-diligence", "concept:trust-level-high"), "trust-factors")
        self.check(asm().replace("concept:trust-level-low", "concept:trust-factor-authority"), "trust-levels")

    def test_status_time_and_topic(self):
        self.check(asm(status="maybe"), "candidate | accepted")
        self.check(asm().replace(f" ; prov:generatedAtTime {T1}", ""), "관찰 시각 누락")
        self.check(asm(factor="authority", topic="llm").replace("concept:topic-llm", "<https://example.org/undefined-topic>"), "어휘 스킴에 속한 개념")

    def test_supersede_must_keep_target_and_factor_be_later_and_not_cycle(self):
        self.ok(asm("aaaaaaaaaaaaaaaa", factor="authority", level="low") + asm("bbbbbbbbbbbbbbbb", factor="authority", level="high", at=T2, supersedes="aaaaaaaaaaaaaaaa"))
        self.check(asm("aaaaaaaaaaaaaaaa") + asm("bbbbbbbbbbbbbbbb", factor="authority", at=T2, supersedes="aaaaaaaaaaaaaaaa"), "대체 관계 위반")
        self.check(asm("aaaaaaaaaaaaaaaa", supersedes="bbbbbbbbbbbbbbbb") + asm("bbbbbbbbbbbbbbbb", supersedes="aaaaaaaaaaaaaaaa", at=T2), "대체 관계 위반")
        self.check(asm("aaaaaaaaaaaaaaaa", at=T2) + asm("bbbbbbbbbbbbbbbb", at=T1, supersedes="aaaaaaaaaaaaaaaa"), "대체 관계 위반")
        self.check(asm("aaaaaaaaaaaaaaaa", at=T1) + asm("bbbbbbbbbbbbbbbb", at=T1, supersedes="aaaaaaaaaaaaaaaa"), "대체 관계 위반")

    def test_derived_trust_is_not_stored(self):
        self.check(f"{DOC} sa:effectiveTrust concept:trust-level-high .\n", "파생값 저장 금지")
        self.check(f"{KARP} sa:currentTrust concept:trust-level-high .\n", "파생값 저장 금지")

    def test_iri_pattern(self):
        self.check(asm("short"), "TrustFactorAssessment IRI")


class QueryTest(unittest.TestCase):
    def rows(self, ttl, topic=None, doc=DOC_DATA):
        g = SAT.BASE + Graph().parse(data=PRE + TOPICS + doc + ttl, format="turtle")
        b = {"doc": URIRef("https://example.org/doc1")}
        if topic: b["topic"] = URIRef(C + f"topic-{topic}")
        short = lambda x: None if x is None else str(x).rsplit("-", 1)[-1]
        out = []
        for r in g.query(QUERY, initBindings=b):
            pub = None if r.publisher is None else str(r.publisher).rsplit("/", 1)[-1]
            out.append(dict(publisher=pub, authority=short(r.authority), authorityFrom=str(r.authorityFrom), diligence=short(r.diligence),
                            diligenceFrom=str(r.diligenceFrom), trust=short(r.trust), status=str(r.trustStatus),
                            aDis=bool(r.authorityDisagreement) if r.authorityDisagreement is not None else None,
                            dDis=bool(r.diligenceDisagreement) if r.diligenceDisagreement is not None else None))
        return out

    def one(self, ttl, **kw):
        rows = self.rows(ttl, **kw)
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def test_without_assessments_authority_is_unknown_and_trust_is_not_computed(self):
        r = self.one("")
        self.assertEqual((r["authority"], r["authorityFrom"]), (None, "unknown"))       # 공신력은 문서 유형의 기본값이 없다
        self.assertEqual((r["diligence"], r["diligenceFrom"]), ("high", "prior"))         # 성실도는 문서 유형의 기본값이 있다
        self.assertEqual((r["trust"], r["status"]), (None, "unknown"))                    # 모르는 값은 채우지 않는다

    def test_the_3x3_table_is_enforced_for_every_combination(self):
        for (a, d), expected in TABLE.items():
            with self.subTest(authority=a, diligence=d):
                r = self.one(asm("aaaaaaaaaaaaaaaa", factor="authority", level=a) + asm("bbbbbbbbbbbbbbbb", factor="diligence", level=d))
                self.assertEqual((r["authority"], r["diligence"], r["trust"], r["status"]), (a, d, expected, "computed"))

    def test_table_is_symmetric_weakest_side_and_matches_its_documentation(self):
        levels = ["low", "medium", "high"]
        for a, d in itertools.product(levels, levels):
            self.assertEqual(TABLE[(a, d)], levels[min(levels.index(a), levels.index(d))])
            self.assertEqual(TABLE[(a, d)], TABLE[(d, a)])

    def test_any_unknown_factor_leaves_trust_uncomputed_even_when_the_other_is_low(self):
        # 한쪽이 낮음이면 결과도 낮을 것이라고 추론할 수 있지만, 이 구조는 모르는 요인이 하나라도 있으면 채우지 않는다.
        r = self.one(asm(factor="diligence", level="low"))                                        # 공신력 모름 + 성실도 낮음
        self.assertEqual((r["authority"], r["diligence"], r["trust"], r["status"]), (None, "low", None, "unknown"))
        no_type = f"{DOC} dcterms:publisher {KARP} .\n"                                           # 문서 유형이 없어 성실도 기본값도 없다
        r = self.one(asm(factor="authority", level="high"), doc=no_type)                          # 공신력 높음 + 성실도 모름
        self.assertEqual((r["authority"], r["diligence"], r["diligenceFrom"], r["trust"], r["status"]), ("high", None, "unknown", None, "unknown"))
        r = self.one("", doc=no_type)                                                              # 둘 다 모름
        self.assertEqual((r["trust"], r["status"]), (None, "unknown"))

    def test_diligence_prior_is_used_only_when_no_assessment_applies(self):
        r = self.one(asm("aaaaaaaaaaaaaaaa", factor="authority", level="high"))
        self.assertEqual((r["diligence"], r["diligenceFrom"], r["trust"]), ("high", "prior", "high"))
        r = self.one(asm("aaaaaaaaaaaaaaaa", factor="authority", level="high") + asm("bbbbbbbbbbbbbbbb", factor="diligence", level="low"))
        self.assertEqual((r["diligence"], r["diligenceFrom"], r["trust"]), ("low", "assessment", "low"))

    def test_candidate_and_rejected_do_not_apply(self):
        r = self.one(asm(factor="authority", level="high", status="candidate") + asm("bbbbbbbbbbbbbbbb", factor="authority", level="high", status="rejected"))
        self.assertEqual((r["authority"], r["status"]), (None, "unknown"))

    def test_unknown_publisher_never_borrows_another_agents_assessment(self):
        # 발행자를 모르는 문서에 다른 사람의 공신력 평가가 새어 들어가면 안 된다.
        r = self.one(asm(factor="authority", level="high"), doc=f"{DOC} dcterms:type concept:source-type-paper .\n")
        self.assertEqual((r["publisher"], r["authority"], r["authorityFrom"], r["trust"], r["status"]), (None, None, "unknown", None, "unknown"))
        self.assertEqual((r["diligence"], r["diligenceFrom"]), ("high", "prior"))

    def test_each_publisher_gets_their_own_authority_and_trust(self):
        doc = DOC_DATA + f"{DOC} dcterms:creator {OTHER} .\n" + f"{OTHER} a sa:Person .\n"
        data = asm("aaaaaaaaaaaaaaaa", factor="authority", level="high") + asm("bbbbbbbbbbbbbbbb", factor="authority", level="low", target=f"sa:assessesAgent {OTHER}")
        rows = {r["publisher"]: r for r in self.rows(data, doc=doc)}
        self.assertEqual((rows["andrej-karpathy"]["authority"], rows["andrej-karpathy"]["trust"]), ("high", "high"))
        self.assertEqual((rows["other-author"]["authority"], rows["other-author"]["trust"]), ("low", "low"))

    def test_topic_specific_beats_general_even_when_older(self):
        data = asm("aaaaaaaaaaaaaaaa", factor="authority", level="high", at=T3) + asm("bbbbbbbbbbbbbbbb", factor="authority", level="low", at=T1, topic="llm")
        self.assertEqual((self.one(data, topic="llm")["authority"], self.one(data, topic="llm")["trust"]), ("low", "low"))
        self.assertEqual(self.one(data)["authority"], "high")
        self.assertEqual(self.one(data, topic="tax")["authority"], "high")

    def test_topic_only_assessment_is_unknown_for_other_topics(self):
        data = asm(factor="authority", level="high", topic="llm")
        self.assertEqual((self.one(data, topic="tax")["authority"], self.one(data, topic="tax")["status"]), (None, "unknown"))
        self.assertEqual(self.one(data)["authority"], None)
        self.assertEqual(self.one(data, topic="llm")["authority"], "high")

    def test_later_assessment_and_supersession_replace_earlier_ones(self):
        later = asm("aaaaaaaaaaaaaaaa", factor="authority", level="low", at=T1) + asm("bbbbbbbbbbbbbbbb", factor="authority", level="high", at=T3)
        self.assertEqual(self.one(later)["authority"], "high")
        sup = asm("aaaaaaaaaaaaaaaa", factor="authority", level="high", at=T3) + asm("bbbbbbbbbbbbbbbb", factor="authority", level="low", at=T1, supersedes="aaaaaaaaaaaaaaaa")
        self.assertEqual(self.one(sup)["authority"], "low")           # 조회 쪽 방어: 모순된 대체 선언도 명시가 우선(SHACL 이 이런 데이터를 막는다)

    def test_same_time_conflicting_levels_are_kept_and_flagged_per_factor(self):
        rows = self.rows(asm("aaaaaaaaaaaaaaaa", factor="authority", level="high") + asm("bbbbbbbbbbbbbbbb", factor="authority", level="low"))
        self.assertEqual(sorted((r["authority"], r["aDis"]) for r in rows), [("high", True), ("low", True)])
        rows = self.rows(asm("aaaaaaaaaaaaaaaa", factor="diligence", level="high") + asm("bbbbbbbbbbbbbbbb", factor="diligence", level="low"))
        self.assertEqual(sorted((r["diligence"], r["dDis"]) for r in rows), [("high", True), ("low", True)])

    def test_trust_is_never_a_statistical_value(self):
        # 결과는 낮음·중·높음 중 하나이거나 계산 불가다. 숫자나 확률이 나오지 않는다.
        seen = {r["trust"] for a in ("low", "medium", "high") for d in ("low", "medium", "high")
                for r in self.rows(asm("aaaaaaaaaaaaaaaa", factor="authority", level=a) + asm("bbbbbbbbbbbbbbbb", factor="diligence", level=d))}
        self.assertEqual(seen, {"low", "medium", "high"})


if __name__ == "__main__":
    unittest.main()
