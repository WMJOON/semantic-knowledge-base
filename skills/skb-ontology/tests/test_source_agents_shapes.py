"""source-agents.shapes.ttl 회귀 테스트: 승인된 정책이 실제로 강제되는지 확인한다.

실제 스키마·어휘 TTL 위에 정상/위반 사례를 얹는다. 실행: python -m unittest test_source_agents_shapes -v
"""
import unittest
from pathlib import Path

try:
    from pyshacl import validate
    from rdflib import Graph
except ImportError as e:  # skb-ontology/requirements.txt 의 pyshacl·rdflib 가 없으면 건너뛴다
    raise unittest.SkipTest(f"pyshacl/rdflib 필요: {e}")

D = Path(__file__).resolve().parent.parent / "references" / "domains" / "source-agents"
SHAPES = Graph().parse(D / "source-agents.shapes.ttl", format="turtle")
BASE = Graph().parse(D / "source-agents.ttl", format="turtle") + Graph().parse(D / "source-agents-vocabulary.ttl", format="turtle")

PRE = """
@prefix sa: <https://skb.dev/ontology/source-agents#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix org: <http://www.w3.org/ns/org#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix concept: <https://skb.dev/ontology/source-agents/concept#> .
@prefix ex: <https://example.org/skb/x#> .
"""
M_STRONG_REG = "concept:identity-method-third-party-register"
M_STRONG_VER = "concept:identity-method-platform-verified"
M_MED = "concept:identity-method-org-official-listing"
M_WEAK = "concept:identity-method-self-declared-bio"

ACCOUNT = """
<https://example.org/skb/account/github/150920049> a sa:Account ; sa:platform "github" ; sa:platformAccountId "150920049" ;
    sa:handle "unslothai" ; sa:platformVerified true ; sa:declaredBio "bio" ;
    prov:hadPrimarySource <https://api.github.com/orgs/unslothai> ; prov:generatedAtTime "2026-09-30T01:00:00Z"^^xsd:dateTime .
"""
MENTION = """
<https://example.org/skb/mention/0123456789abcdef> a sa:AgentMention ; sa:declaredName "unslothai" ; sa:declaredType "Organization" ; sa:inDocument <https://example.org/doc> ;
    sa:mentionRole concept:source-agent-role-publisher ; sa:observedAccount <https://example.org/skb/account/github/150920049> ;
    sa:isMemberOfHostOrg false ; prov:generatedAtTime "2026-09-30T01:00:00Z"^^xsd:dateTime .
"""


def claim(methods=(M_STRONG_REG,), status="accepted", reviewed=True, about="sa:aboutAccount <https://example.org/skb/account/github/150920049>",
          identity="<https://example.org/skb/org/unsloth>", evidence=True, cid="<https://example.org/skb/identification/0123456789abcdef>"):
    parts = [f"{cid} a sa:MentionIdentification ; {about} ; sa:identifiesAs {identity} ; sa:identificationStatus \"{status}\" ;"
             " sa:assessedAt \"2026-09-30T02:00:00Z\"^^xsd:dateTime ;"]
    parts.append(" ".join(f"sa:identificationMethod {m} ;" for m in methods))
    if evidence:
        parts.append("sa:identificationEvidence <https://www.wikidata.org/wiki/Q1> ;")
    if reviewed:
        parts.append("sa:reviewedBy <https://example.org/skb/person/reviewer> ;")
    return "\n".join(parts).rstrip(";") + " .\n"


PA = PRE + ACCOUNT                        # sa:aboutAccount 의 범위가 Account 라 RDFS 추론으로 참조 노드가 Account 가 된다 → 계정을 정의해 둔다
ORG = "<https://example.org/skb/org/unsloth> a sa:Organization .\n"
PERSON = "<https://example.org/skb/person/andrej-karpathy> a sa:Person .\n"
VALID = PRE + ACCOUNT + MENTION + ORG + claim()


def run(ttl):
    data = BASE + Graph().parse(data=ttl, format="turtle")
    ok, _, text = validate(data, shacl_graph=SHAPES, inference="rdfs", advanced=True)
    return ok, text


class PolicyTest(unittest.TestCase):
    def check(self, ttl, expect):
        ok, text = run(ttl)
        self.assertFalse(ok, "위반을 놓침")
        self.assertIn(expect, text)

    # ---- 정상 사례
    def test_valid(self):
        ok, text = run(VALID)
        self.assertTrue(ok, text[:900])

    def test_real_vocabulary_alone_conforms_and_paper_has_only_a_diligence_prior(self):
        ok, text = run(PRE)
        self.assertTrue(ok, text[:600])
        from rdflib import URIRef
        sa, c = "https://skb.dev/ontology/source-agents#", "https://skb.dev/ontology/source-agents/concept#"
        paper = URIRef(c + "source-type-paper")
        # 성실도 기본값만 문서 유형에 붙는다(값은 재검토 중인 출발 가정). 공신력은 발행자에 붙으므로 문서 유형에 기본값이 없다.
        self.assertEqual(list(BASE.objects(paper, URIRef(sa + "defaultDiligence"))), [URIRef(c + "trust-level-high")])
        for gone in ("defaultAuthority", "defaultDocumentCredibility", "defaultAuthorCredibility", "defaultCredibilityLevel"):
            self.assertEqual(list(BASE.objects(paper, URIRef(sa + gone))), [], gone)

    def test_accepted_with_one_strong_method_is_enough(self):
        for m in (M_STRONG_REG, M_STRONG_VER):
            ok, text = run(PA + ORG + claim(methods=(m,)))
            self.assertTrue(ok, f"{m}: {text[:500]}")

    def test_accepted_with_two_distinct_methods_is_enough(self):
        ok, text = run(PA + ORG + claim(methods=(M_MED, M_WEAK)))
        self.assertTrue(ok, text[:500])

    def test_candidate_needs_no_review_and_no_sufficiency(self):
        ok, text = run(PA + ORG + claim(methods=(M_WEAK,), status="candidate", reviewed=False))
        self.assertTrue(ok, text[:500])

    # ---- Account
    def test_account_violations(self):
        cases = {
            "불변 ID 없음": (VALID.replace('sa:platformAccountId "150920049" ;', ""), "platformAccountId"),
            "IRI 를 핸들로 만듦": (VALID.replace("https://example.org/skb/account/github/150920049>", "https://example.org/skb/account/github/unslothai>", 1), "계정 IRI"),
            "소개 300자 초과": (VALID.replace('sa:declaredBio "bio"', 'sa:declaredBio "%s"' % ("x" * 301)), "300자"),
            "인증 표시가 문자열": (VALID.replace("sa:platformVerified true", 'sa:platformVerified "yes"'), "platformVerified"),
            "관찰 시각 없음": (VALID.replace('prov:generatedAtTime "2026-09-30T01:00:00Z"^^xsd:dateTime .\n\n<https://example.org/skb/mention/0123456789abcdef>', 'sa:handle "unslothai" .\n\n<https://example.org/skb/mention/0123456789abcdef>'), "관찰 시각"),
        }
        for name, (ttl, expect) in cases.items():
            with self.subTest(name):
                ok, text = run(ttl)
                self.assertFalse(ok, name)
                self.assertIn(expect, text)

    def test_account_without_source_fails(self):
        self.check(VALID.replace("prov:hadPrimarySource <https://api.github.com/orgs/unslothai> ;", ""), "출처 누락")

    # ---- AgentMention
    def test_mention_violations(self):
        cases = {
            "선언 유형이 허용 밖": (VALID.replace('sa:declaredType "Organization"', 'sa:declaredType "Company"'), "declaredType"),
            "역할이 스킴 밖": (VALID.replace("concept:source-agent-role-publisher", "concept:trust-level-low"), "source-agent-roles"),
            "문서 없음": (VALID.replace("sa:inDocument <https://example.org/doc> ;", ""), "inDocument"),
            "이름 없음": (VALID.replace('sa:declaredName "unslothai" ;', ""), "declaredName"),
            "정의되지 않은 계정을 참조": (VALID.replace("sa:observedAccount <https://example.org/skb/account/github/150920049>", "sa:observedAccount ex:ghost"), "platformAccountId"),
        }
        for name, (ttl, expect) in cases.items():
            with self.subTest(name):
                ok, text = run(ttl)
                self.assertFalse(ok, name)
                self.assertIn(expect, text)

    # ---- MentionIdentification
    def test_claim_target_must_be_exactly_one(self):
        both = claim(about="sa:aboutAccount <https://example.org/skb/account/github/150920049> ; sa:aboutMention <https://example.org/skb/mention/0123456789abcdef>")
        self.check(PRE + ACCOUNT + MENTION + ORG + both, "정확히 하나")
        self.check(PA + ORG + claim(about=""), "정확히 하나")

    def test_accepted_requires_human_review(self):
        self.check(PA + ORG + claim(reviewed=False), "검토 누락")

    def test_accepted_with_only_self_declared_bio_is_rejected(self):
        self.check(PA + ORG + claim(methods=(M_WEAK,)), "근거 부족")

    def test_accepted_with_single_medium_method_is_not_enough(self):
        self.check(PA + ORG + claim(methods=(M_MED,)), "근거 부족")

    def test_strength_grouping_concept_is_not_a_method(self):
        self.check(PA + ORG + claim(methods=("concept:identity-method-strength-strong",), status="candidate", reviewed=False), "구체 방법")

    def test_claim_needs_evidence_valid_status_and_person_or_org(self):
        self.check(PA + ORG + claim(evidence=False), "근거 누락")
        self.check(PA + ORG + claim(status="maybe"), "identificationStatus")
        self.check(PA + "ex:thing a sa:Account .\n" + claim(identity="ex:thing"), "identifiesAs")

    # ---- 프라이버시: Person
    def test_person_requires_accepted_strong_or_medium_evidence(self):
        ok, text = run(PA + PERSON + claim(identity="<https://example.org/skb/person/andrej-karpathy>", methods=(M_STRONG_REG,)))
        self.assertTrue(ok, text[:500])
        ok, text = run(PA + PERSON + claim(identity="<https://example.org/skb/person/andrej-karpathy>", methods=(M_MED, M_WEAK)))            # 중간 근거 포함
        self.assertTrue(ok, text[:500])

    def test_person_without_claims_or_only_candidate_is_rejected(self):
        self.check(PRE + PERSON, "공인 근거 없음")
        self.check(PA + PERSON + claim(identity="<https://example.org/skb/person/andrej-karpathy>", status="candidate", reviewed=False), "공인 근거 없음")

    def test_person_with_only_weak_self_declared_evidence_is_rejected(self):
        ok, text = run(PA + PERSON + claim(identity="<https://example.org/skb/person/andrej-karpathy>", methods=(M_WEAK,)))
        self.assertFalse(ok)
        self.assertIn("공인 근거 없음", text)

    def test_organization_needs_no_person_grade_evidence(self):
        ok, text = run(PRE + ORG)
        self.assertTrue(ok, text[:500])

    # ---- Membership
    MEMBER = ("<https://example.org/skb/membership/aaaaaaaaaaaaaaaa> a org:Membership , sa:Membership ; org:member <https://example.org/skb/person/andrej-karpathy> ; org:organization <https://example.org/skb/org/unsloth> ; "
              "org:role concept:source-agent-role-author ; sa:memberSince \"2023-01-01\"^^xsd:date ; sa:startStatus \"known\" ; sa:endStatus \"open\" ; "
              "prov:generatedAtTime \"2026-09-30T01:00:00Z\"^^xsd:dateTime ; prov:hadPrimarySource <https://example.org/x> .\n")

    def test_membership_valid_and_time_bound(self):
        ok, text = run(PA + PERSON + ORG + claim(identity="<https://example.org/skb/person/andrej-karpathy>") + self.MEMBER)
        self.assertTrue(ok, text[:600])

    def test_membership_unknown_dates_are_explicit_not_blank(self):
        base = PA + PERSON + ORG + claim(identity="<https://example.org/skb/person/andrej-karpathy>")
        unknown = self.MEMBER.replace('sa:memberSince "2023-01-01"^^xsd:date ; sa:startStatus "known" ; sa:endStatus "open"', 'sa:startStatus "unknown" ; sa:endStatus "unknown"')
        ok, text = run(base + unknown)
        self.assertTrue(ok, text[:600])
        ended = self.MEMBER.replace('sa:endStatus "open"', 'sa:endStatus "ended" ; sa:memberUntil "2024-01-01"^^xsd:date')
        ok, text = run(base + ended)
        self.assertTrue(ok, text[:600])
        self.check(base + self.MEMBER.replace('sa:endStatus "open"', 'sa:endStatus "ended"'), "종료 상태 불일치")
        self.check(base + self.MEMBER.replace('sa:endStatus "open"', 'sa:endStatus "open" ; sa:memberUntil "2024-01-01"^^xsd:date'), "종료 상태 불일치")

    def test_conflicting_memberships_are_both_kept(self):
        base = PA + PERSON + ORG + claim(identity="<https://example.org/skb/person/andrej-karpathy>")
        other = self.MEMBER.replace("aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb")
        a = self.MEMBER.replace(" prov:hadPrimarySource", " sa:conflictsWith <https://example.org/skb/membership/bbbbbbbbbbbbbbbb> ; prov:hadPrimarySource")
        ok, text = run(base + a + other)
        self.assertTrue(ok, text[:600])

    def test_current_membership_query_keeps_conflicts(self):
        from rdflib import Literal, XSD
        q = (D / "queries" / "current_membership.rq").read_text(encoding="utf-8")
        A = self.MEMBER
        B = self.MEMBER.replace("aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb").replace("org/unsloth", "org/other").replace("2023-01-01", "2024-06-01")
        C = self.MEMBER.replace("aaaaaaaaaaaaaaaa", "cccccccccccccccc").replace('sa:endStatus "open"', 'sa:endStatus "ended" ; sa:memberUntil "2023-06-01"^^xsd:date')
        g = Graph().parse(data=PRE + A + B + C + "<https://example.org/skb/membership/aaaaaaaaaaaaaaaa> sa:conflictsWith <https://example.org/skb/membership/bbbbbbbbbbbbbbbb> .\n", format="turtle")
        rows = list(g.query(q, initBindings={"asOf": Literal("2025-01-01", datatype=XSD.date)}))
        ids = sorted(str(r.membership)[-16:] for r in rows)
        self.assertEqual(ids, ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"])        # 종료된 c 는 빠지고, 충돌하는 a·b 는 둘 다 남는다
        self.assertTrue(all(bool(r.hasConflict) for r in rows))
        rows = list(g.query(q, initBindings={"asOf": Literal("2023-03-01", datatype=XSD.date)}))
        self.assertEqual(sorted(str(r.membership)[-16:] for r in rows), ["aaaaaaaaaaaaaaaa", "cccccccccccccccc"])

    def test_stored_current_membership_is_forbidden(self):
        base = PA + PERSON + ORG + claim(identity="<https://example.org/skb/person/andrej-karpathy>") + self.MEMBER
        self.check(base + "<https://example.org/skb/person/andrej-karpathy> org:memberOf <https://example.org/skb/org/unsloth> .\n", "파생값 저장 금지")
        self.check(base + "<https://example.org/skb/person/andrej-karpathy> sa:currentMemberOf <https://example.org/skb/org/unsloth> .\n", "파생값 저장 금지")

    def test_membership_violations(self):
        base = PA + PERSON + ORG + claim(identity="<https://example.org/skb/person/andrej-karpathy>")
        self.check(base + self.MEMBER.replace('sa:memberSince "2023-01-01"^^xsd:date ;', ""), "시작 상태 불일치")
        self.check(base + self.MEMBER.replace('sa:startStatus "known" ;', ""), "유효 시간 누락")
        self.check(base + self.MEMBER.replace('prov:generatedAtTime "2026-09-30T01:00:00Z"^^xsd:dateTime ;', ""), "관찰 시각 누락")
        self.check(base + self.MEMBER.replace(" prov:hadPrimarySource", ' sa:memberUntil "2020-01-01"^^xsd:date ; prov:hadPrimarySource'), "앞선다")
        self.check(base + self.MEMBER.replace("org:member <https://example.org/skb/person/andrej-karpathy>", "org:member <https://example.org/skb/org/unsloth>"), "org:member")
        self.check(base + self.MEMBER.replace("; prov:hadPrimarySource <https://example.org/x>", ""), "출처 누락")

    # ---- 성실도 기본값은 문서 유형에만 붙는다(공신력은 발행자에 붙는다)
    def test_diligence_default_only_on_source_types(self):
        self.check(PA + PERSON + claim(identity="<https://example.org/skb/person/andrej-karpathy>")
                   + "<https://example.org/skb/person/andrej-karpathy> sa:defaultDiligence concept:trust-level-high .\n", "에이전트")

    def test_diligence_level_must_come_from_the_levels_scheme(self):
        self.check(PRE + "concept:source-type-paper sa:defaultDiligence concept:source-type-paper .\n", "trust-levels")

    def test_diligence_default_takes_at_most_one_value(self):
        self.check(PRE + "concept:source-type-paper sa:defaultDiligence concept:trust-level-low .\n"
                   + "concept:source-type-paper sa:defaultDiligence concept:trust-level-medium .\n", "1개여야 한다")

    # ---- IRI 린트: skb-ontology 명명 게이트(N1~N4)가 모르는 인스턴스 IRI 관례
    def test_instance_iri_lint(self):
        strong = (M_STRONG_REG,)
        def person(iri):   # Person 은 공인 근거가 있어야 하므로 accepted 식별을 함께 둔다
            return PA + f"{iri} a sa:Person .\n" + claim(identity=iri, methods=strong)
        bad = {
            "Person 대문자 슬러그": person("<https://example.org/skb/person/Andrej-Karpathy>"),
            "Person 끝 슬래시": person("<https://example.org/skb/person/andrej-karpathy/>"),
            # base 는 사용자가 정하므로 호스트·접두는 검사하지 않는다. 종류 경로(/person/)가 없으면 위반이다.
            "Person 종류 경로 없음": person("<https://example.org/skb/people/andrej-karpathy>"),
            "Person 블랭크 노드": person("_:p"),
            "Person 이 org 경로": person("<https://example.org/skb/org/andrej-karpathy>"),
            "Organization 이 person 경로": PA + "<https://example.org/skb/person/unsloth> a sa:Organization .\n",
            "Organization 대문자": PA + "<https://example.org/skb/org/Unsloth> a sa:Organization .\n",
            "Account 플랫폼 대문자": VALID.replace("https://example.org/skb/account/github/150920049", "https://example.org/skb/account/GitHub/150920049"),
            "AgentMention 해시가 16자가 아님": VALID.replace("mention/0123456789abcdef", "mention/0123456789abcde"),
            "AgentMention 해시에 대문자": VALID.replace("mention/0123456789abcdef", "mention/0123456789ABCDEF"),
            "MentionIdentification 해시가 16자가 아님": VALID.replace("identification/0123456789abcdef", "identification/0123456789abcdef0"),
        }
        for name, ttl in bad.items():
            with self.subTest(name):
                ok, text = run(ttl)
                self.assertFalse(ok, f"IRI 위반을 놓침: {name}")
                self.assertIn("IRI", text)

    def test_wellformed_instance_iris_pass(self):
        ok, text = run(PA + "<https://example.org/skb/org/unsloth-ai> a sa:Organization .\n")
        self.assertTrue(ok, text[:500])

    def test_membership_iri_lint(self):
        base = PA + PERSON + ORG + claim(identity="<https://example.org/skb/person/andrej-karpathy>")
        ok, text = run(base + self.MEMBER.replace("membership/aaaaaaaaaaaaaaaa", "membership/short"))
        self.assertFalse(ok); self.assertIn("IRI 형식", text)


if __name__ == "__main__":
    unittest.main()
