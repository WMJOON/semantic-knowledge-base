#!/usr/bin/env python3
"""저자 신원 해소(HITL): propose → (사람이 결정) → apply → check.

  propose  등록(evidence/registrations)에서 결정적 후보 큐를 만든다(evidence/identity/review-queue.jsonl). 모델·네트워크 없음.
  apply    사람이 쓴 evidence/identity/decisions.jsonl 만 읽어 현재 accepted 인 식별을 evidence/identity/identifications.ttl 로 투영한다.
  check    identifications.ttl 이 결정 로그의 투영과 같은지(손 편집 탐지) + 도메인 SHACL 을 다시 확인한다.

불변식: 도구는 accepted 를 스스로 만들지 않는다. decisions.jsonl 은 사람이 쓰고, reviewer 가 없거나 에이전트로 보이는 값이면 거부한다.
reject/revoke 는 로그에만 남고(재제안 억제·감사), 그래프에는 현재 accepted 인 식별만 있다.

decisions.jsonl 한 줄:
  {"target"|"targets": IRI|[IRI], "decision": "accept|reject|revoke", "identity": {"kind": "Person|Organization", "slug": "jane-doe", "label": "Jane Doe"},
   "methods": ["platform-verified", ...], "evidence": ["https://..."], "reviewer": "<사람 이름>", "decided_at": "2026-10-06T09:00:00Z", "note": "(선택)"}
accept 는 identity·methods·evidence 필수. reject 는 identity 선택. revoke 는 accept 였던 대상에만.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import identity_lib as L  # noqa: E402
import layout as _layout  # noqa: E402

_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def read_decisions(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                d = json.loads(line)
            except ValueError as e:
                raise ValueError(f"decisions.jsonl:{n}: JSON 오류 ({e})")
            d["_line"] = n
            out.append(d)
    return out


def _targets(d: dict) -> list[str]:
    t = d.get("targets") or ([d["target"]] if d.get("target") else [])
    return [str(x) for x in t]


def validate_decisions(decisions: list[dict], known_targets: dict[str, str]) -> tuple[dict, list[str]]:
    """결정 로그 → (대상별 현재 상태, 오류). 상태 기계: 없음→accept|reject, accept→revoke, reject→accept, revoke→accept."""
    methods = L.method_names()
    errors: list[str] = []
    state: dict[str, dict] = {}
    for d in decisions:
        ln = f"decisions.jsonl:{d['_line']}"
        kind = d.get("decision")
        if kind not in ("accept", "reject", "revoke"):
            errors.append(f"{ln}: decision 은 accept|reject|revoke"); continue
        reviewer = (d.get("reviewer") or "").strip()
        if not reviewer:
            errors.append(f"{ln}: reviewer 누락(사람이 적어야 한다)"); continue
        if any(w in reviewer.lower() for w in L.AGENT_LIKE):
            errors.append(f"{ln}: reviewer '{reviewer}' 가 에이전트·모델 이름으로 보인다(사람만 승인할 수 있다)"); continue
        if not _ISO.match(d.get("decided_at", "")):
            errors.append(f"{ln}: decided_at 은 UTC ISO(예: 2026-10-06T09:00:00Z)"); continue
        tg = _targets(d)
        if not tg:
            errors.append(f"{ln}: target(s) 누락"); continue
        bad = [t for t in tg if t not in known_targets]
        if bad:
            errors.append(f"{ln}: 등록에 없는 대상 {bad[0]}"); continue
        ident = d.get("identity")
        if kind == "accept" or ident:
            if not isinstance(ident, dict) or ident.get("kind") not in ("Person", "Organization") or not _SLUG.match(ident.get("slug", "")):
                errors.append(f"{ln}: identity 는 kind(Person|Organization)와 소문자-슬러그 slug 가 필요"); continue
        if kind == "accept":
            ms = d.get("methods") or []
            unknown = [m for m in ms if m not in methods]
            ev = d.get("evidence") or []
            if not ms or unknown:
                errors.append(f"{ln}: methods 는 {sorted(methods)} 중에서 1개 이상(알 수 없음: {unknown})"); continue
            if not ev or any(not re.match(r"^https?://", str(e)) for e in ev):
                errors.append(f"{ln}: evidence 는 http(s) IRI 1개 이상"); continue
        for t in tg:
            cur = state.get(t, {}).get("decision")
            if kind == "revoke" and cur != "accept":
                errors.append(f"{ln}: revoke 는 accept 였던 대상에만 ({t})"); break
            if kind == "accept" and cur == "accept" and state[t].get("identity") != ident:
                errors.append(f"{ln}: 이미 다른 정체성으로 accepted 인 대상이다. 먼저 revoke 한다 ({t})"); break
            if kind == "reject" and cur == "accept":
                errors.append(f"{ln}: accepted 대상은 reject 가 아니라 revoke 로 되돌린다 ({t})"); break
        else:
            for t in tg:
                state[t] = {**d, "target_kind": known_targets[t]}
    return state, errors


def known_targets(reg) -> dict[str, str]:
    from rdflib import Namespace, RDF
    SA = Namespace(L.SA_NS)
    out = {str(a): "account" for a in reg.subjects(RDF.type, SA.Account)}
    out.update({str(m): "mention" for m in reg.subjects(RDF.type, SA.AgentMention)})
    return out


def build_identity_graph(state: dict, base: str):
    from rdflib import Graph, Literal, Namespace, RDF, URIRef
    from rdflib.namespace import PROV, RDFS, XSD
    SA, C = Namespace(L.SA_NS), Namespace(L.CONCEPT_NS)
    B = Namespace(base)
    meth = L.method_names()
    g = Graph()
    for p, n in (("sa", SA), ("concept", C), ("prov", PROV), ("xsd", XSD), ("rdfs", RDFS)):
        g.bind(p, n)
    for t, d in sorted(state.items()):
        if d["decision"] != "accept":
            continue
        ident = d["identity"]
        who = B[("person/" if ident["kind"] == "Person" else "org/") + ident["slug"]]
        g.add((who, RDF.type, SA.Person if ident["kind"] == "Person" else SA.Organization))
        if ident.get("label"):
            g.add((who, RDFS.label, Literal(ident["label"])))
        iid = B["identification/" + hashlib.sha256(f"{t}|{who}".encode()).hexdigest()[:16]]
        g.add((iid, RDF.type, SA.MentionIdentification))
        g.add((iid, SA.aboutAccount if d["target_kind"] == "account" else SA.aboutMention, URIRef(t)))
        g.add((iid, SA.identifiesAs, who))
        g.add((iid, SA.identificationStatus, Literal("accepted")))
        for m in sorted(d["methods"]):
            g.add((iid, SA.identificationMethod, URIRef(meth[m])))
        for e in sorted(d["evidence"]):
            g.add((iid, SA.identificationEvidence, URIRef(e)))
        g.add((iid, SA.reviewedBy, B["reviewer/" + re.sub(r"[^a-z0-9]+", "-", d["reviewer"].lower()).strip("-")]))
        g.add((iid, SA.assessedAt, Literal(d["decided_at"], datatype=XSD.dateTime)))
    return g


def propose(reg, ident, decisions_state: dict, max_clusters: int) -> list[dict]:
    from rdflib import Namespace, RDF, URIRef
    from rdflib.namespace import DCTERMS
    SA = Namespace(L.SA_NS)
    resolved = L.accepted_resolution(reg, ident)
    settled = {t for t, d in decisions_state.items() if d["decision"] in ("accept", "reject")}
    docs = {m: str(next(reg.objects(m, SA.inDocument), "")) for m in reg.subjects(RDF.type, SA.AgentMention)}
    url_of = {d: str(next(reg.objects(d, DCTERMS.source), d)) for d in set(docs.values()) if d}
    rows: list[dict] = []
    # 계정 후보: 그 계정을 관찰한 모든 mention 이 한 번에 해소된다
    obs: dict = collections.defaultdict(list)
    for m in reg.subjects(SA.observedAccount, None):
        for a in reg.objects(m, SA.observedAccount):
            obs[a].append(m)
    for a in sorted(reg.subjects(RDF.type, SA.Account), key=str):
        if str(a) in settled:
            continue
        ms = obs.get(a, [])
        if ms and all(m in resolved for m in ms):
            continue
        rows.append({"target": str(a), "target_kind": "account", "platform": str(next(reg.objects(a, SA.platform), "")),
                     "handle": str(next(reg.objects(a, SA.handle), "")), "mentions": sorted(str(m) for m in ms),
                     "documents": len({docs[m] for m in ms}), "declared_names": sorted({str(n) for m in ms for n in reg.objects(m, SA.declaredName)}),
                     "declared_types": sorted({str(n) for m in ms for n in reg.objects(m, SA.declaredType)}),
                     "reason": f"계정을 관찰한 언급 {len(ms)}개", "hint": "단서일 뿐 근거가 아니다"})
    # 이름 군집 후보: 계정 없는 저자 mention 을 (이름, 소속)으로 묶는다. 제안일 뿐 자동 병합하지 않는다.
    clusters: dict = collections.defaultdict(list)
    for m in reg.subjects(SA.mentionRole, URIRef(L.ROLE_AUTHOR)):
        if m in resolved or str(m) in settled or any(True for _ in reg.objects(m, SA.observedAccount)):
            continue
        name = str(next(reg.objects(m, SA.declaredName), ""))
        aff = str(next(reg.objects(m, SA.declaredAffiliation), ""))
        clusters[(L.norm_name(name), L.norm_name(aff))].append(m)
    crow = []
    for (n, aff), ms in clusters.items():
        crow.append({"targets": sorted(str(m) for m in ms), "target_kind": "mention_cluster", "documents": len({docs[m] for m in ms}),
                     "declared_name": str(next(reg.objects(ms[0], SA.declaredName), "")), "declared_affiliation": aff or None,
                     "reason": "이름이 같은 저자 언급(동일인 보장 없음)", "hint": "같은 이름이 다른 사람일 수 있다"})
    crow.sort(key=lambda r: (-r["documents"], r["declared_name"].casefold(), r["targets"][0]))
    rows += crow[:max_clusters]
    rows.sort(key=lambda r: (r["target_kind"] != "account", -r["documents"], r.get("handle") or r.get("declared_name") or ""))
    for r in rows:
        r["total_clusters"] = len(crow) if r["target_kind"] == "mention_cluster" else None
    return rows


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="identity")
    ap.add_argument("cmd", choices=["propose", "apply", "check"])
    ap.add_argument("--target", default=".")
    ap.add_argument("--base", default="https://example.org/skb/", help="인스턴스 IRI 접두(끝 슬래시 포함)")
    ap.add_argument("--max-clusters", type=int, default=50, help="propose: 이름 군집 후보 상한(영향 문서 수 순)")
    ap.add_argument("--apply", action="store_true", help="propose/apply: 파일을 쓴다(기본 dry-run)")
    a = ap.parse_args(argv)
    target = Path(a.target).resolve()
    lay = _layout.resolve_layout(target)
    idir = lay["identity_dir"]
    reg = L.load_dir_graph(lay["registrations_dir"])
    if not len(reg):
        print("ERROR: 등록이 없다. 먼저 `skb-evidence register --apply`", file=sys.stderr)
        return 1
    try:
        decisions = read_decisions(idir / "decisions.jsonl")
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    state, errors = validate_decisions(decisions, known_targets(reg))
    if errors:
        for e in errors[:20]:
            print("ERROR:", e, file=sys.stderr)
        return 2
    graph_path = idir / "identifications.ttl"

    if a.cmd == "propose":
        rows = propose(reg, L.load_file_graph(graph_path), state, a.max_clusters)
        summ = collections.Counter(r["target_kind"] for r in rows)
        print(json.dumps({"queue": dict(summ), "total": len(rows)}, ensure_ascii=False))
        if a.apply:
            idir.mkdir(parents=True, exist_ok=True)
            (idir / "review-queue.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
            print(f"written: {_layout.rel(target, idir)}/review-queue.jsonl (결정은 decisions.jsonl 에 사람이 쓴다)")
        else:
            print("dry-run: 파일을 쓰지 않았다. --apply 로 큐를 쓴다.", file=sys.stderr)
        return 0

    from register import shacl_check
    g = build_identity_graph(state, a.base)
    ok, text = shacl_check(g)
    if a.cmd == "apply":
        accepted = sum(1 for d in state.values() if d["decision"] == "accept")
        print(json.dumps({"decisions": len(decisions), "accepted_targets": accepted, "shacl_conforms": ok}, ensure_ascii=False))
        if not ok:
            print(text[:1500], file=sys.stderr)
            return 2
        if a.apply:
            idir.mkdir(parents=True, exist_ok=True)
            graph_path.write_text(g.serialize(format="turtle"), encoding="utf-8")
            print(f"written: {_layout.rel(target, graph_path)}")
        else:
            print("dry-run: 파일을 쓰지 않았다. --apply 로 쓴다.", file=sys.stderr)
        return 0

    # check: 결정 로그의 투영과 파일이 같아야 한다(손 편집 탐지) + SHACL
    from rdflib.compare import isomorphic
    on_disk = L.load_file_graph(graph_path)
    problems = []
    if not ok:
        problems.append("SHACL 위반:\n" + text[:800])
    if not isomorphic(g, on_disk):
        problems.append("identifications.ttl 이 decisions.jsonl 의 투영과 다르다(손으로 고쳤거나 apply 를 다시 하지 않았다)")
    print(json.dumps({"accepted_targets": sum(1 for d in state.values() if d["decision"] == "accept"), "problems": len(problems)}, ensure_ascii=False))
    for p in problems:
        print(" -", p, file=sys.stderr)
    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
