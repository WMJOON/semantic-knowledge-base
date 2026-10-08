"""identity propose/apply/check: 결정적 후보 큐, 사람이 쓴 결정만 반영, 불변식(자동 accepted 없음), 손 편집 탐지."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_register as R  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
PY = R.PY
ACCT_JDOE = "https://example.org/skb/account/github/99"
ACCT_ACME = "https://example.org/skb/account/github/1234"
EV = ["https://orcid.org/0000-0000-0000-0001"]


def dec(target, decision="accept", kind="Person", slug="jane-doe", methods=("platform-verified",), reviewer="Won Joon",
        at="2026-10-06T09:00:00Z", evidence=EV, **extra):
    d = {"decision": decision, "reviewer": reviewer, "decided_at": at, **extra}
    d["targets" if isinstance(target, list) else "target"] = target
    if slug:
        d["identity"] = {"kind": kind, "slug": slug, "label": slug}
    if decision == "accept":
        d["methods"], d["evidence"] = list(methods), list(evidence)
    return d


@unittest.skipUnless(R.HAVE_DEPS, "rdflib/pyshacl 필요")
class IdentityTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.t = Path(self.td.name)
        (self.t / "evidence/raw").mkdir(parents=True)
        (self.t / "evidence/raw/a.md").write_text(R.RAW, encoding="utf-8")
        with open(self.t / "evidence/seeds.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps(R.seed(1, "https://github.com/acme/tool")) + "\n")
        for script in ("catalog.py", "register.py"):
            r = subprocess.run([PY, str(SCRIPTS / script), "--target", str(self.t), "--apply"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        self.td.cleanup()

    def run_id(self, cmd, *extra):
        return subprocess.run([PY, str(SCRIPTS / "identity.py"), cmd, "--target", str(self.t), *extra], capture_output=True, text=True)

    def idir(self):
        return self.t / "evidence/identity"

    def write_decisions(self, *ds):
        self.idir().mkdir(parents=True, exist_ok=True)
        (self.idir() / "decisions.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in ds), encoding="utf-8")

    def queue(self):
        self.run_id("propose", "--apply")
        return [json.loads(x) for x in (self.idir() / "review-queue.jsonl").read_text(encoding="utf-8").splitlines()]

    def graph(self):
        p = self.idir() / "identifications.ttl"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # ---- propose
    def test_propose_dry_run_writes_nothing(self):
        r = self.run_id("propose")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.idir().exists())

    def test_propose_writes_only_the_queue(self):
        self.queue()
        self.assertEqual(sorted(p.name for p in self.idir().iterdir()), ["review-queue.jsonl"])

    def test_queue_has_accounts_and_name_cluster_without_merging_account_authors(self):
        q = self.queue()
        kinds = [r["target_kind"] for r in q]
        self.assertEqual(kinds.count("account"), 2)
        clusters = [r for r in q if r["target_kind"] == "mention_cluster"]
        self.assertEqual([c["declared_name"] for c in clusters], ["Kim Lee"])  # Jane Doe 는 계정으로 해소 가능하므로 군집에서 제외
        self.assertEqual(len(clusters[0]["targets"]), 1)

    def test_queue_is_deterministic(self):
        first = self.queue()
        self.assertEqual(first, self.queue())

    def test_max_clusters_caps_cluster_rows(self):
        r = self.run_id("propose", "--apply", "--max-clusters", "0")
        self.assertEqual(r.returncode, 0)
        q = [json.loads(x) for x in (self.idir() / "review-queue.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertFalse([x for x in q if x["target_kind"] == "mention_cluster"])

    def test_queue_never_contains_decisions(self):
        for row in self.queue():
            self.assertNotIn("decision", row)
            self.assertNotIn("reviewer", row)

    # ---- apply: 불변식
    def test_no_decisions_yields_empty_projection(self):
        r = self.run_id("apply", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("sa:Person", self.graph())

    def test_accept_projects_person_and_identification(self):
        self.write_decisions(dec(ACCT_JDOE))
        r = self.run_id("apply", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        g = self.graph()
        for needle in ("sa:Person", "sa:MentionIdentification", "sa:aboutAccount", 'sa:identificationStatus "accepted"',
                       "sa:reviewedBy", "identity-method-platform-verified"):
            self.assertIn(needle, g)

    def test_missing_reviewer_is_rejected(self):
        self.write_decisions(dec(ACCT_JDOE, reviewer=""))
        r = self.run_id("apply", "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertIn("reviewer", r.stderr)
        self.assertEqual(self.graph(), "")

    def test_agent_like_reviewer_is_rejected(self):
        for who in ("claude", "Codex CLI", "gemma-4", "my-agent"):
            self.write_decisions(dec(ACCT_JDOE, reviewer=who))
            r = self.run_id("apply", "--apply")
            self.assertEqual(r.returncode, 2, who)
            self.assertIn("에이전트", r.stderr)

    def test_weak_single_method_is_rejected_by_shapes_and_writes_nothing(self):
        self.write_decisions(dec(ACCT_JDOE, methods=("self-declared-bio",)))
        r = self.run_id("apply", "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.graph(), "")

    def test_duplicate_weak_method_does_not_count_as_two_methods(self):
        self.write_decisions(dec(ACCT_JDOE, methods=("self-declared-bio", "self-declared-bio")))
        self.assertEqual(self.run_id("apply", "--apply").returncode, 2)

    def test_organization_accepts_medium_plus_weak(self):
        self.write_decisions(dec(ACCT_ACME, kind="Organization", slug="acme", methods=("org-official-listing", "self-declared-bio")))
        r = self.run_id("apply", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sa:Organization", self.graph())

    def test_unknown_target_is_rejected(self):
        self.write_decisions(dec("https://example.org/skb/account/github/0"))
        r = self.run_id("apply", "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertIn("등록에 없는 대상", r.stderr)

    def test_unknown_method_and_missing_evidence_are_rejected(self):
        self.write_decisions(dec(ACCT_JDOE, methods=("vibes",)))
        self.assertEqual(self.run_id("apply").returncode, 2)
        self.write_decisions(dec(ACCT_JDOE, evidence=[]))
        self.assertEqual(self.run_id("apply").returncode, 2)

    def test_dry_run_apply_writes_nothing(self):
        self.write_decisions(dec(ACCT_JDOE))
        r = self.run_id("apply")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.graph(), "")

    def test_apply_is_idempotent_and_deterministic(self):
        self.write_decisions(dec(ACCT_JDOE))
        self.run_id("apply", "--apply")
        first = self.graph()
        self.run_id("apply", "--apply")
        self.assertEqual(first, self.graph())

    # ---- 상태 기계
    def test_revoke_requires_prior_accept(self):
        self.write_decisions(dec(ACCT_JDOE, decision="revoke"))
        self.assertEqual(self.run_id("apply").returncode, 2)

    def test_accepted_target_cannot_be_rejected_only_revoked(self):
        self.write_decisions(dec(ACCT_JDOE), dec(ACCT_JDOE, decision="reject", at="2026-10-06T10:00:00Z"))
        r = self.run_id("apply")
        self.assertEqual(r.returncode, 2)
        self.assertIn("revoke", r.stderr)

    def test_conflicting_second_accept_requires_revoke(self):
        self.write_decisions(dec(ACCT_JDOE), dec(ACCT_JDOE, slug="john-roe", at="2026-10-06T10:00:00Z"))
        self.assertEqual(self.run_id("apply").returncode, 2)

    def test_revoke_removes_person_from_projection_and_requeues_target(self):
        self.write_decisions(dec(ACCT_JDOE), dec(ACCT_JDOE, decision="revoke", at="2026-10-06T10:00:00Z"))
        r = self.run_id("apply", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("sa:Person", self.graph())
        self.assertIn(ACCT_JDOE, [x.get("target") for x in self.queue()])

    def test_reject_suppresses_requeue_and_is_not_in_graph(self):
        self.write_decisions(dec(ACCT_JDOE, decision="reject", slug=None))
        self.assertEqual(self.run_id("apply", "--apply").returncode, 0)
        self.assertNotIn("sa:Person", self.graph())
        self.assertNotIn(ACCT_JDOE, [x.get("target") for x in self.queue()])

    def test_accept_after_reject_is_allowed(self):
        self.write_decisions(dec(ACCT_JDOE, decision="reject", slug=None), dec(ACCT_JDOE, at="2026-10-06T10:00:00Z"))
        self.assertEqual(self.run_id("apply", "--apply").returncode, 0)
        self.assertIn("sa:Person", self.graph())

    def test_accepted_account_leaves_queue_with_its_mentions_resolved(self):
        self.write_decisions(dec(ACCT_JDOE))
        self.run_id("apply", "--apply")
        q = self.queue()
        self.assertNotIn(ACCT_JDOE, [x.get("target") for x in q])

    def test_cluster_decision_creates_one_identification_per_mention(self):
        cl = [r for r in self.queue() if r["target_kind"] == "mention_cluster"][0]
        self.write_decisions(dec(cl["targets"], slug="kim-lee", methods=("third-party-register",)))
        self.assertEqual(self.run_id("apply", "--apply").returncode, 0)
        self.assertEqual(self.graph().count("a sa:MentionIdentification"), len(cl["targets"]))

    # ---- check
    def test_check_passes_after_apply(self):
        self.write_decisions(dec(ACCT_JDOE))
        self.run_id("apply", "--apply")
        r = self.run_id("check")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_check_detects_hand_edited_projection(self):
        self.write_decisions(dec(ACCT_JDOE))
        self.run_id("apply", "--apply")
        p = self.idir() / "identifications.ttl"
        p.write_text(p.read_text(encoding="utf-8").replace("jane-doe", "someone-else"), encoding="utf-8")
        r = self.run_id("check")
        self.assertEqual(r.returncode, 2)
        self.assertIn("투영과 다르다", r.stderr)

    def test_check_detects_added_acceptance_not_in_log(self):
        self.write_decisions(dec(ACCT_JDOE))
        self.run_id("apply", "--apply")
        self.write_decisions()  # 로그를 비웠는데 파일에는 accepted 가 남아 있다
        self.assertEqual(self.run_id("check").returncode, 2)

    # ---- 카탈로그 연결: 상태·개수 계산, 재계산 게이트
    def rebuild_catalog(self):
        r = subprocess.run([PY, str(SCRIPTS / "catalog.py"), "--target", str(self.t), "--apply"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def cat_validate(self):
        return subprocess.run([PY, str(SCRIPTS / "catalog_validate.py"), "--target", str(self.t)], capture_output=True, text=True)

    def cat_ttl(self):
        return (self.t / "evidence/catalog/catalog.ttl").read_text(encoding="utf-8")

    def test_catalog_without_identification_is_partial_with_counts(self):
        t = self.cat_ttl()
        self.assertIn('ec:authorshipState "partial"', t)
        self.assertIn("ec:authorMentionCount 2", t)
        self.assertIn("ec:authorResolvedCount 0", t)
        self.assertNotIn("dcterms:creator", t)
        self.assertEqual(self.cat_validate().returncode, 0)

    def test_one_of_two_authors_resolved_stays_partial_and_lists_creator(self):
        self.write_decisions(dec(ACCT_JDOE))
        self.run_id("apply", "--apply")
        self.rebuild_catalog()
        t = self.cat_ttl()
        self.assertIn('ec:authorshipState "partial"', t)
        self.assertIn("ec:authorResolvedCount 1", t)
        self.assertIn("person/jane-doe", t)
        r = self.cat_validate()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_all_authors_resolved_becomes_resolved(self):
        cl = [r for r in self.queue() if r["target_kind"] == "mention_cluster"][0]
        self.write_decisions(dec(ACCT_JDOE), dec(cl["targets"], slug="kim-lee", methods=("third-party-register",)))
        self.run_id("apply", "--apply")
        self.rebuild_catalog()
        t = self.cat_ttl()
        self.assertIn('ec:authorshipState "resolved"', t)
        self.assertIn("ec:authorResolvedCount 2", t)
        self.assertEqual(self.cat_validate().returncode, 0)

    def test_revoke_returns_catalog_to_partial(self):
        self.write_decisions(dec(ACCT_JDOE), dec(ACCT_JDOE, decision="revoke", at="2026-10-06T10:00:00Z"))
        self.run_id("apply", "--apply")
        self.rebuild_catalog()
        self.assertIn("ec:authorResolvedCount 0", self.cat_ttl())

    def test_stale_catalog_after_apply_is_caught(self):
        self.write_decisions(dec(ACCT_JDOE))
        self.run_id("apply", "--apply")  # catalog 를 다시 만들지 않음
        r = self.cat_validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("저자 해소 수 불일치", r.stderr)

    def test_hand_edited_resolved_state_is_caught(self):
        p = self.t / "evidence/catalog/catalog.ttl"
        p.write_text(self.cat_ttl().replace('ec:authorshipState "partial"', 'ec:authorshipState "resolved"'), encoding="utf-8")
        r = self.cat_validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("SHACL", r.stderr)

    def test_hand_added_creator_is_caught(self):
        p = self.t / "evidence/catalog/catalog.ttl"
        t = self.cat_ttl()
        t = t.replace("ec:authorMentionCount 2", "dcterms:creator <https://example.org/skb/person/ghost> ;\n    ec:authorMentionCount 2", 1)
        p.write_text(t, encoding="utf-8")
        self.assertEqual(self.cat_validate().returncode, 1)

    def test_apply_requires_registrations(self):
        import shutil
        shutil.rmtree(self.t / "evidence/registrations")
        self.assertEqual(self.run_id("propose").returncode, 1)


if __name__ == "__main__":
    unittest.main()
