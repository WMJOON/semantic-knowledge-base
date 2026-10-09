"""identity 공용: 등록(관찰 층)과 식별 그래프(해석 층)를 읽어 문서별 저자 해소 정보를 계산한다. rdflib 필요."""
from __future__ import annotations

import unicodedata
from pathlib import Path

SA_NS = "https://skb.dev/ontology/source-agents#"
CONCEPT_NS = "https://skb.dev/ontology/source-agents/concept#"
ROLE_AUTHOR = CONCEPT_NS + "source-agent-role-author"
ROLE_PUBLISHER = CONCEPT_NS + "source-agent-role-publisher"
PACK = Path(__file__).resolve().parents[2] / "skb-ontology" / "references" / "domains" / "source-agents"
AGENT_LIKE = ("claude", "codex", "gpt", "gemma", "gemini", "luna", "llm", "agent", "bot", "assistant", "copilot", "sol")


def norm_name(s: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", s).casefold().split())


def load_dir_graph(d: Path):
    from rdflib import Graph
    g = Graph()
    if d.is_dir():
        for f in sorted(d.glob("*.ttl")):
            g.parse(f, format="turtle")
    return g


def load_file_graph(path: Path):
    from rdflib import Graph
    g = Graph()
    if path.is_file():
        g.parse(path, format="turtle")
    return g


def method_names() -> dict[str, str]:
    """구체 근거 방법 이름 → 개념 IRI (identity-methods 스킴, 강도 묶음 제외)."""
    from rdflib import Graph, Namespace, URIRef
    from rdflib.namespace import SKOS
    g = Graph().parse(PACK / "source-agents-vocabulary.ttl", format="turtle")
    scheme = URIRef("https://skb.dev/ontology/source-agents/concept-scheme/identity-methods")
    out = {}
    for c in g.subjects(SKOS.inScheme, scheme):
        loc = str(c).split("#")[-1]
        if loc.startswith("identity-method-") and not loc.startswith("identity-method-strength-"):
            out[loc[len("identity-method-"):]] = str(c)
    return out


def accepted_resolution(reg, ident):
    """등록 그래프 + 식별 그래프 → (해소된 mention IRI 집합, mention → [identity IRI]).
    mention 이 해소됨 = accepted 식별이 그 mention 또는 그 mention 이 관찰한 계정을 가리킴."""
    from rdflib import Namespace
    SA = Namespace(SA_NS)
    acc_by_target: dict = {}
    for i in ident.subjects(SA.identificationStatus, None):
        if str(next(ident.objects(i, SA.identificationStatus))) != "accepted":
            continue
        who = next(ident.objects(i, SA.identifiesAs), None)
        for pred in (SA.aboutMention, SA.aboutAccount):
            for t in ident.objects(i, pred):
                acc_by_target.setdefault(t, []).append(who)
    resolved: dict = {}
    for m in set(reg.subjects(SA.mentionRole, None)):
        ids = list(acc_by_target.get(m, []))
        for a in reg.objects(m, SA.observedAccount):
            ids += acc_by_target.get(a, [])
        if ids:
            resolved[m] = sorted({str(x) for x in ids if x is not None})
    return resolved


def doc_author_info(reg, ident) -> dict[str, dict]:
    """문서 URL(dcterms:source) → {mentions:int, resolved:int, creators:[Person/Org IRI]} (role=author 언급만)."""
    from rdflib import Namespace, URIRef
    from rdflib.namespace import DCTERMS
    SA = Namespace(SA_NS)
    resolved = accepted_resolution(reg, ident)
    url_of = {d: str(next(reg.objects(d, DCTERMS.source), "")) for d in set(reg.objects(None, SA.inDocument))}
    out: dict[str, dict] = {}
    for m in reg.subjects(SA.mentionRole, URIRef(ROLE_AUTHOR)):
        d = next(reg.objects(m, SA.inDocument), None)
        url = url_of.get(d, "")
        if not url:
            continue
        rec = out.setdefault(url, {"mentions": 0, "resolved": 0, "creators": set()})
        rec["mentions"] += 1
        if m in resolved:
            rec["resolved"] += 1
            rec["creators"].update(resolved[m])
    for rec in out.values():
        rec["creators"] = sorted(rec["creators"])
    return out
