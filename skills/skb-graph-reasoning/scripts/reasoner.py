"""OWL 2 RL reasoning over canonical Turtle (rdflib + owlrl). 순수 로직 — CLI 는 graph_reasoning.py.

정본은 asserted TTL(ontology/system/semantic/<domain>/*.ttl)이고, 추론 결과(*.inferred.ttl)는 언제든 지우고 다시 만드는 파생물이다.
OWL 2 RL 은 규칙 기반 프로파일이다: 서브클래스·서브프로퍼티 전이, 도메인/레인지 타이핑, inverse/symmetric/transitive,
sameAs, 함수형 프로퍼티, 그리고 disjointWith·differentFrom·cardinality 위반 같은 비일관성 탐지를 다룬다.
OWL DL 의 완전한 클래스 충족 가능성 검사(HermiT 등)는 하지 않는다.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import owlrl
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, XSD

ERR = Namespace("http://www.daml.org/2002/03/agents/agent-ont#")  # owlrl 이 비일관성 메시지에 쓰는 어휘
SKIP_SUFFIXES = (".shapes.ttl", ".inferred.ttl")
XSD_CLASH = re.compile(r"Disjoint classes http://www\.w3\.org/2001/XMLSchema#\w+ and http://www\.w3\.org/2001/XMLSchema#\w+ have a common individual")
STANDARD_PREFIXES = ("http://www.w3.org/", "https://www.w3.org/", "http://purl.org/", "https://purl.org/")
HEADER_HASH = re.compile(r"^# source-hash: (sha256:[0-9a-f]{64})\s*$", re.M)


def semantic_root(target: Path) -> Path:
    return Path(target).resolve() / "ontology" / "system" / "semantic"


def asserted_files(target: Path, domain: Optional[str] = None) -> List[Path]:
    """skb-ontology 의 asserted_files 와 같은 규칙: 도메인 하위의 *.ttl, shapes·inferred 제외."""
    root = semantic_root(target)
    scope = root / domain.strip("/") if domain else root
    if not scope.exists():
        return []
    return sorted(p for p in scope.rglob("*.ttl") if not p.name.endswith(SKIP_SUFFIXES))


def inferred_path(target: Path, domain: str) -> Path:
    clean = domain.strip("/")
    return semantic_root(target) / clean / (Path(clean).name + ".inferred.ttl")


def load_graph(paths: Iterable[Path]) -> Graph:
    g = Graph()
    for p in paths:
        g.parse(p, format="turtle")
    return g


def source_hash(target: Path, paths: Iterable[Path]) -> str:
    """asserted 원천의 내용 지문. 파일이 바뀌면 달라진다."""
    h = hashlib.sha256()
    root = Path(target).resolve()
    for p in sorted(paths):
        h.update(str(p.relative_to(root)).encode() + b"\0" + hashlib.sha256(p.read_bytes()).hexdigest().encode() + b"\n")
    return "sha256:" + h.hexdigest()


def split_errors(errors: List[str]) -> Tuple[List[str], List[str]]:
    """(논리적 비일관성, XSD 값 공간 아티팩트). 같은 어휘형 "1" 이 문자열과 숫자로 함께 쓰이면 owlrl 이
    xsd:decimal 과 xsd:string 의 disjoint 위반으로 보고하는데, 지식 그래프의 모순이 아니라 데이터형 표기 문제다."""
    logical = [e for e in errors if not XSD_CLASH.match(e)]
    return logical, [e for e in errors if XSD_CLASH.match(e)]


def _is_trivial(s, p, o) -> bool:
    """owlrl 이 모든 용어에 대해 쏟아내는 의미 없는 파생 트리플.

    리터럴이 주어인 트리플(Turtle 로 쓸 수 없다)과 W3C·purl 표준 어휘 자체에 대한 트리플(xsd:integer a rdfs:Datatype 등)도 뺀다.
    """
    if isinstance(s, Literal):
        return True
    if isinstance(s, URIRef) and str(s).startswith(STANDARD_PREFIXES):
        return True
    if p in (OWL.sameAs, OWL.equivalentClass, OWL.equivalentProperty, RDFS.subClassOf, RDFS.subPropertyOf) and s == o:
        return True
    if p == RDF.type and o in (OWL.Thing, RDFS.Resource):
        return True
    if p == RDFS.subClassOf and o in (OWL.Thing, RDFS.Resource):
        return True
    return False


def closure(asserted: Graph, rdfs: bool = False) -> Tuple[Graph, List[str], List[str]]:
    """(폐포, 논리적 비일관성 메시지, XSD 아티팩트 메시지). 입력 그래프는 바꾸지 않는다."""
    expanded = Graph()
    for t in asserted:
        expanded.add(t)
    cls = owlrl.return_closure_class(True, rdfs, False)
    cls(expanded, False, False, rdfs=rdfs).closure()
    errors: List[str] = []
    for msg in set(expanded.subjects(RDF.type, ERR.ErrorMessage)):
        errors.extend(str(v) for v in expanded.objects(msg, ERR.error))
        for t in list(expanded.triples((msg, None, None))):
            expanded.remove(t)
    logical, artifacts = split_errors(sorted(set(errors)))
    return expanded, logical, artifacts


def infer(asserted: Graph, keep_trivial: bool = False, rdfs: bool = False) -> Tuple[Graph, List[str], List[str]]:
    """(파생 트리플만 담은 그래프, 논리적 비일관성, XSD 아티팩트)."""
    expanded, errors, artifacts = closure(asserted, rdfs=rdfs)
    out = Graph()
    for ns_prefix, ns in asserted.namespaces():
        out.bind(ns_prefix, ns)
    for t in expanded:
        if t in asserted:
            continue
        if not keep_trivial and _is_trivial(*t):
            continue
        out.add(t)
    return out, errors, artifacts


def categorize(inferred: Graph) -> Dict[str, int]:
    names = {RDF.type: "type", RDFS.subClassOf: "subClassOf", RDFS.subPropertyOf: "subPropertyOf", OWL.sameAs: "sameAs",
             OWL.equivalentClass: "equivalentClass", OWL.equivalentProperty: "equivalentProperty", OWL.inverseOf: "inverseOf"}
    c: Counter = Counter()
    for _, p, _ in inferred:
        c[names.get(p, "property assertion")] += 1
    return dict(c)


def write_inferred(target: Path, domain: str, inferred: Graph, fingerprint: str, files: List[Path], rdfs: bool = False) -> Path:
    """파생 TTL 을 쓴다. 맨 위 주석에 원천 지문을 남겨 status 가 파일 전체를 파싱하지 않고 신선도를 판정한다."""
    root = Path(target).resolve()
    g = Graph()
    for p, ns in inferred.namespaces():
        g.bind(p, ns)
    g.bind("prov", PROV)
    g.bind("dcterms", DCTERMS)
    for t in inferred:
        g.add(t)
    act = URIRef("urn:skb:inference:" + domain.strip("/").replace("/", ":"))
    g.add((act, RDF.type, PROV.Activity))
    g.add((act, DCTERMS.description, Literal("OWL 2 RL closure by owlrl %s%s (derived; regenerate, do not edit)" % (owlrl.__version__ if hasattr(owlrl, "__version__") else "?", " + RDFS" if rdfs else ""))))
    g.add((act, DCTERMS.identifier, Literal(fingerprint)))
    for f in files:
        g.add((act, PROV.used, URIRef("urn:skb:source:" + str(f.relative_to(root)))))
    path = inferred_path(target, domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = g.serialize(format="turtle")
    header = ("# GENERATED by skb-graph-reasoning (OWL 2 RL). Derived from asserted Turtle; never edit.\n"
              "# source-hash: %s\n# triples: %d\n" % (fingerprint, len(inferred)))
    path.write_text(header + body, encoding="utf-8")
    return path


def status(target: Path, domain: str) -> Dict[str, object]:
    """fresh | stale | missing. 파생 TTL 헤더의 지문과 현재 asserted 지문을 비교한다."""
    path = inferred_path(target, domain)
    files = asserted_files(target, domain)
    if not path.exists():
        return {"domain": domain, "state": "missing", "path": str(path)}
    m = HEADER_HASH.search(path.read_text(encoding="utf-8")[:1000])
    now = source_hash(target, files)
    if not m:
        return {"domain": domain, "state": "stale", "path": str(path), "reason": "no source-hash header"}
    if m.group(1) != now:
        return {"domain": domain, "state": "stale", "path": str(path), "reason": "asserted source changed since inference"}
    return {"domain": domain, "state": "fresh", "path": str(path)}


def query(asserted: Graph, sparql: str, with_closure: bool = True, rdfs: bool = False):
    """asserted(+폐포)에 SPARQL 을 실행한다. 폐포가 켜져 있으면 sameAs·서브클래스 전이 같은 파생이 질의에 보인다."""
    graph = closure(asserted, rdfs=rdfs)[0] if with_closure else asserted
    return graph.query(sparql)
