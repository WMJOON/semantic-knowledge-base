#!/usr/bin/env python3
"""카탈로그의 문서·저자 선언을 source-agents 도메인의 관찰 층(AgentMention·Account)으로 등록한다. 모델·네트워크 없음.

만든다  : 문서(prov:Entity), 원문 스냅샷(내용 해시 IRI), sa:AgentMention(저자·문서가 선언한 발행 주체), sa:Account(관찰된 플랫폼 계정)
만들지 않는다: Person, MentionIdentification, TrustFactorAssessment, 모델이 쓴 triple. 신원 해소·신뢰 평가는 후속 HITL 단계다.
저자가 없으면 저자를 만들지 않는다(authorshipReason 은 카탈로그에 이미 있다). domain-derived 발행 주체는 문서가 선언한 것이 아니므로 만들지 않는다.

입력  : evidence/catalog/catalog.ttl 의 ec:Source 중 ec:rawPath 가 있는 것 + 그 raw frontmatter(날짜·저자·계정 선언값)
출력  : evidence/registrations/<document-key>.ttl  (기본 dry-run, --apply 로 쓴다)
        관찰 데이터(언급·계정)는 문서마다 쌓이므로 skb-ontology 의 term 레지스트리 계약(인스턴스 선언) 대신 이 도구의 SHACL 게이트로 검증한다.
        카탈로그(evidence/catalog)와 같은 층이다. 신원 해소로 승격된 Person/Organization 은 사람 검토 뒤 ontology/system/semantic/source-agents 에 둔다.

검사(결정적): ① lexical(대체문자·제어/숨은 문자·비정상 공백·mojibake·NFC) ② SHACL(references/domains/source-agents 의 shapes)
같은 문서·같은 스냅샷은 기존 등록을 보존한다. 같은 문서의 내용이 바뀌었으면 등록을 중단한다.
종료 코드 0: dry-run 통과/등록/이미 등록. 2: lexical error, SHACL 위반, 내용 변경 충돌.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as _layout  # noqa: E402
from catalog import parse_frontmatter  # noqa: E402

SA_NS = "https://skb.dev/ontology/source-agents#"
CONCEPT_NS = "https://skb.dev/ontology/source-agents/concept#"
EC_NS = "https://skb.dev/ontology/evidence-catalog#"
PACK = Path(__file__).resolve().parents[2] / "skb-ontology" / "references" / "domains" / "source-agents"
_ID_OK = re.compile(r"^[A-Za-z0-9_.:-]+$")
_MOJIBAKE = re.compile(r"Ã[\u0080-¿]|â€[\u0080-¿™œ“”]|Â[ -¿]")
_INVISIBLE = {"​", "‌", "‍", "⁠", "﻿", "‮", "‭"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lexical_findings(name: str) -> list[dict]:
    """이름 문자열을 바꾸지 않고 의심 지점만 보고한다. level=error 는 등록을 막는다."""
    out: list[dict] = []
    if "�" in name:
        out.append({"level": "error", "code": "replacement-char", "value": name})
    bad = [c for c in name if unicodedata.category(c) == "Cc" or c in _INVISIBLE]
    if bad:
        out.append({"level": "error", "code": "control-or-hidden-char", "value": name})
    if _MOJIBAKE.search(name):
        out.append({"level": "warning", "code": "mojibake-candidate", "value": name})
    if unicodedata.normalize("NFC", name) != name:
        out.append({"level": "warning", "code": "not-nfc", "value": name})
    if name != name.strip() or re.search(r"\s{2,}|[  - 　]", name):
        out.append({"level": "warning", "code": "irregular-whitespace", "value": name})
    return out


def _json_list(v: str | None) -> list:
    try:
        x = json.loads(v or "")
        return x if isinstance(x, list) else []
    except ValueError:
        return []


def build_registration(source_url: str, title: str | None, fm: dict, raw_bytes: bytes, base: str):
    """(graph, doc_key, snapshot_iri, findings, notes). 파일 쓰기 없음."""
    from rdflib import Graph, Literal, Namespace, RDF, URIRef
    from rdflib.namespace import DCTERMS, XSD
    SA, C, PROV = Namespace(SA_NS), Namespace(CONCEPT_NS), Namespace("http://www.w3.org/ns/prov#")
    B = Namespace(base)
    g = Graph()
    for p, n in (("sa", SA), ("concept", C), ("prov", PROV), ("dcterms", DCTERMS), ("xsd", XSD)):
        g.bind(p, n)
    doc_key = sha(source_url.encode("utf-8"))[:24]
    doc = B["document/" + doc_key]
    snap = B["source-snapshot/" + sha(raw_bytes)]
    collected = fm.get("collected_at")
    findings: list[dict] = []
    notes: list[str] = []
    if not collected:
        raise ValueError("raw 원문에 collected_at 이 없다(verify 먼저)")
    ts = Literal(collected, datatype=XSD.dateTime)
    g.add((doc, RDF.type, PROV.Entity))
    g.add((doc, DCTERMS.source, Literal(source_url, datatype=XSD.anyURI)))
    if title:
        g.add((doc, DCTERMS.title, Literal(title)))
    g.add((doc, PROV.wasDerivedFrom, snap))
    g.add((snap, RDF.type, PROV.Entity))

    accounts: dict[tuple[str, str], URIRef] = {}
    for a in _json_list(fm.get("accounts")):
        plat, ident = str(a.get("platform", "")).lower(), str(a.get("id", ""))
        if not plat or not _ID_OK.match(ident):
            notes.append(f"account skipped (불변 id 없음): {a.get('platform')}/{a.get('handle')}")
            continue
        u = B[f"account/{plat}/{ident}"]
        g.add((u, RDF.type, SA.Account))
        g.add((u, SA.platform, Literal(plat)))
        g.add((u, SA.platformAccountId, Literal(ident)))
        g.add((u, SA.handle, Literal(str(a.get("handle", "")))))
        g.add((u, PROV.hadPrimarySource, snap))
        g.add((u, PROV.generatedAtTime, ts))
        accounts[(plat, str(a.get("handle", "")).lower())] = u

    def mention(name: str, dtype: str, role: str, affiliation: str | None, account: URIRef | None):
        for f in lexical_findings(name):
            findings.append({**f, "role": role})
        mid = sha(f"{doc_key}|{role}|{name}".encode("utf-8"))[:16]
        m = B["mention/" + mid]
        g.add((m, RDF.type, SA.AgentMention))
        g.add((m, SA.declaredName, Literal(name, datatype=XSD.string)))
        g.add((m, SA.declaredType, Literal(dtype)))
        g.add((m, SA.inDocument, doc))
        g.add((m, SA.mentionRole, C["source-agent-role-" + role]))
        g.add((m, PROV.generatedAtTime, ts))
        g.add((m, PROV.wasDerivedFrom, snap))
        if affiliation:
            g.add((m, SA.declaredAffiliation, Literal(affiliation)))
        if account is not None:
            g.add((m, SA.observedAccount, account))

    for au in _json_list(fm.get("authors")):
        if not isinstance(au, dict) or not au.get("name"):
            continue
        acct = None
        if au.get("account"):
            acct = next((u for (pl, h), u in accounts.items() if h == str(au["account"]).lower()), None)
        mention(au["name"], au.get("type") if au.get("type") in ("Person", "Organization") else "unknown",
                "author", au.get("affiliation"), acct)
    pub = fm.get("publisher")
    if pub and fm.get("publisher_source") != "domain-derived":
        ptype = fm.get("publisher_type") if fm.get("publisher_type") in ("Person", "Organization") else "unknown"
        pacct = next((u for (pl, h), u in accounts.items()
                      if any(a.get("role") == "publisher" and str(a.get("handle", "")).lower() == h
                             for a in _json_list(fm.get("accounts")))), None)
        mention(pub, ptype, "publisher", None, pacct)
    elif pub:
        notes.append(f"publisher '{pub}' 은 domain-derived 라 문서가 선언한 것이 아니므로 mention 을 만들지 않았다")
    return g, doc_key, snap, findings, notes


def shacl_check(g) -> tuple[bool, str]:
    from pyshacl import validate
    from rdflib import Graph
    shapes = Graph().parse(PACK / "source-agents.shapes.ttl", format="turtle")
    # 역할·방법·수준 개념(skos:inScheme)은 어휘 파일에 있으므로 데이터 그래프에 합쳐서 검사한다(도메인 pack 의 테스트와 같은 방식).
    data = g + Graph().parse(PACK / "source-agents.ttl", format="turtle") + Graph().parse(PACK / "source-agents-vocabulary.ttl", format="turtle")
    conforms, _, text = validate(data, shacl_graph=shapes, inference="none", advanced=True)
    return bool(conforms), text


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="register")
    ap.add_argument("--target", default=".", help="KB root")
    ap.add_argument("--base", default="https://example.org/skb/", help="인스턴스 IRI 접두(끝 슬래시 포함)")
    ap.add_argument("--source", action="append", help="이 URL 의 문서만 등록(여러 번 가능)")
    ap.add_argument("--apply", action="store_true", help="파일을 쓴다(기본 dry-run)")
    ap.add_argument("--check", action="store_true", help="이미 써 둔 등록 파일 전체를 도메인 SHACL 로 다시 검증한다(손 편집 탐지)")
    a = ap.parse_args(argv)
    from rdflib import Graph, Namespace, RDF
    from rdflib.namespace import DCTERMS
    EC = Namespace(EC_NS)
    target = Path(a.target).resolve()
    lay = _layout.resolve_layout(target)
    cat = lay["catalog_dir"] / "catalog.ttl"
    out_dir = lay["registrations_dir"]
    if a.check:
        bad = 0
        files = sorted(out_dir.glob("*.ttl")) if out_dir.is_dir() else []
        for f in files:
            ok, text = shacl_check(Graph().parse(f, format="turtle"))
            if not ok:
                bad += 1
                print(f"FAIL: {f.name}\n{text[:600]}", file=sys.stderr)
        print(json.dumps({"checked": len(files), "violations": bad}))
        return 2 if bad else 0
    if not cat.exists():
        print("ERROR: 카탈로그가 없다. 먼저 `skb-evidence catalog --apply`", file=sys.stderr)
        return 1
    cg = Graph().parse(cat, format="turtle")
    results, rc = [], 0
    for s in sorted(cg.subjects(RDF.type, EC.Source), key=str):
        raw_rel = next(cg.objects(s, EC.rawPath), None)
        url = next(cg.objects(s, DCTERMS.source), None)
        if raw_rel is None or url is None or (a.source and str(url) not in a.source):
            continue
        raw_path = target / str(raw_rel)
        if not raw_path.is_file():
            results.append({"source": str(url), "status": "error", "reason": f"raw 없음: {raw_rel}"}); rc = 2
            continue
        raw_bytes = raw_path.read_bytes()
        fm = parse_frontmatter(raw_bytes.decode("utf-8", errors="replace"))
        title = next((str(t) for t in cg.objects(s, DCTERMS.title)), None)
        try:
            g, key, snap, findings, notes = build_registration(str(url), title, fm, raw_bytes, a.base)
        except ValueError as e:
            results.append({"source": str(url), "status": "error", "reason": str(e)}); rc = 2
            continue
        rec = {"source": str(url), "document_key": key, "mentions": len(list(g.subjects(RDF.type, Namespace(SA_NS).AgentMention))),
               "accounts": len(list(g.subjects(RDF.type, Namespace(SA_NS).Account))), "lexical": findings, "notes": notes}
        dest = out_dir / f"{key}.ttl"
        if dest.exists():
            existing = Graph().parse(dest, format="turtle")
            if (None, None, snap) in existing:
                rec["status"] = "already_registered"
            else:
                rec["status"] = "conflict"
                rec["reason"] = "같은 문서의 원문 스냅샷이 바뀌었다. 기존 등록을 보존하고 중단한다(버전이 다르면 별도 문서로 등록)"
                rc = 2
            results.append(rec)
            continue
        if any(f["level"] == "error" for f in findings):
            rec["status"] = "lexical_error"; rc = 2
        else:
            ok, text = shacl_check(g)
            if not ok:
                rec["status"] = "shacl_violation"; rec["reason"] = text[:800]; rc = 2
            elif a.apply:
                out_dir.mkdir(parents=True, exist_ok=True)
                dest.write_text(g.serialize(format="turtle"), encoding="utf-8")
                rec["status"] = "registered"
            else:
                rec["status"] = "dry_run_passed"
        results.append(rec)
    print(json.dumps({"results": results}, ensure_ascii=False, indent=1))
    if not a.apply:
        print("dry-run: 파일을 쓰지 않았다. --apply 로 쓴다.", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
