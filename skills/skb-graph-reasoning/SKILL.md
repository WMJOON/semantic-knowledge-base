---
name: skb-graph-reasoning
description: |
  SKB 의 정본 Turtle 위에서 OWL 2 RL 추론을 수행한다 (rdflib + owlrl, Java 불필요).
  파생 트리플을 *.inferred.ttl 로 만들고(reason), 비일관성을 점검하고(check), 무엇이 얼마나 파생되는지 보고하고(stats),
  파생 파일이 최신인지 알려 주고(status), 폐포 위에서 SPARQL 을 실행한다(query).
  정본 TTL 은 수정하지 않는다. 트리거: "추론", "OWL 추론", "reasoner", "비일관성 점검", "inferred", "서브클래스 전이", "SPARQL 질의".
metadata:
  version: "0.1.0"
---

# skb-graph-reasoning (v0.1.0)

## What

정본(asserted) TTL 의 OWL 2 RL 폐포를 계산해 **파생 사실**과 **모순**을 드러내는 추론기.
`skb-ontology` 의 옛 `reason`/`materialize` 를 이관해 확장한 스킬이다.

OWL 2 RL 이 다루는 것: 서브클래스·서브프로퍼티 전이, `rdfs:domain`/`range` 타이핑, `inverseOf`, 대칭·추이 프로퍼티,
`sameAs`, 함수형 프로퍼티, `disjointWith`·`differentFrom`·cardinality 위반 같은 비일관성.
**다루지 않는 것**: OWL DL 의 완전한 클래스 충족 가능성(HermiT 등). 이 환경에는 Java 가 없고, 필요해지면 별도 백엔드로 추가한다.

## 원칙

1. **정본은 asserted TTL 이다.** 쓰는 파일은 `--apply` 일 때의 `<domain>/<name>.inferred.ttl` 하나뿐이고, 언제든 지우고 다시 만든다. 다음 실행에서 이 파일은 입력으로 읽지 않는다.
2. **먼저 검증한다.** `reason` 은 `skb-ontology` 가 형제로 있으면 asserted TTL 을 검증해 실패가 있으면 추론하지 않는다(`--no-validate` 로 건너뜀). 없으면 건너뛴다고 알린다.
3. **모순이 있으면 쓰지 않는다.** 논리적 비일관성이 있으면 종료 코드 3 으로 끝내고 파생 파일을 쓰지 않는다(`--allow-inconsistent` 로 강제).
4. **XSD 아티팩트는 모순이 아니다.** 같은 어휘형 `"1"` 이 문자열과 숫자로 함께 쓰이면 owlrl 이 `xsd:decimal`/`xsd:string` disjoint 위반을 보고한다. 이는 데이터형 표기 문제라 `xsd_artifacts` 로 따로 세고 종료 코드에 넣지 않는다(`check --strict-datatypes` 로 포함).
5. **잡음을 싣지 않는다.** 모든 용어에 대한 반사 트리플(`x sameAs x`, `rdf:type owl:Thing`)과 리터럴·W3C 표준 어휘가 주어인 트리플은 뺀다(`--keep-trivial` 로 유지).
6. **신선도를 헤더로 안다.** 파생 파일 맨 위 주석의 `source-hash` 와 현재 asserted 지문을 비교한다(`status`).

## Entry Points

| 명령 | 설명 |
|---|---|
| `scripts/skb-graph-reasoning reason --target KB --domain D [--apply] [--print] [--keep-trivial] [--rdfs] [--no-validate] [--allow-inconsistent]` | 파생 트리플 계산, `--apply` 면 `.inferred.ttl` 작성 |
| `scripts/skb-graph-reasoning check --target KB [--domain D] [--rdfs] [--json] [--strict-datatypes]` | 비일관성 점검. 있으면 종료 코드 1. 도메인을 빼면 KB 전체 |
| `scripts/skb-graph-reasoning stats --target KB --domain D [--json]` | 규칙 종류별 파생 개수 |
| `scripts/skb-graph-reasoning status --target KB --domain D [--json]` | `fresh \| stale \| missing`, fresh 가 아니면 종료 코드 1 |
| `scripts/skb-graph-reasoning query --target KB [--domain D] (--sparql Q \| --file F) [--no-closure] [--json] [--limit N]` | 폐포 위 SPARQL. ASK 는 종료 코드 0/1 |

`--rdfs` 는 RDFS 규칙을 함께 적용한다. `--domain` 은 `ontology/system/semantic/` 아래 경로다(예: `academic/finance`).

## 환경

`rdflib`, `owlrl` 이 필요하다. 인터프리터 선택: `SKB_GRAPH_REASONING_PYTHON` → 형제 `skb-ontology/.venv` → `python3`. 형제 스킬 위치는 `SKB_SKILL_SKB_ONTOLOGY_HOME` 으로 바꿀 수 있다.

## 알아둘 것

- 파생량은 모델링 방식에 크게 달라진다. SKOS 개념만 있는 도메인은 OWL 공리가 없어 파생이 거의 0건이고, OWL 클래스·개체·프로퍼티 공리가 있는 도메인에서 일한다.
- 큰 KB 에서는 같은 어휘형(`"1"`)이 문자열과 숫자로 함께 쓰여 `xsd_artifacts` 가 나올 수 있다. 논리 모순이 아니다(원칙 4).

## Non-Goals

- 개념·관계 생성과 검증 → `skb-ontology`
- 검색 인덱스 → `skb-semantic-search`
- JSONL 관계층 위 다중 홉 탐색 (옛 `msm-graph-reasoning`) — 이 스킬은 정본 TTL 만 읽는다.
- OWL DL 추론기(HermiT/Pellet), 파생 사실의 정당화(justification) 추적

## 테스트

`python -m pytest -q tests` (18개, `skb-ontology/.venv` 로 실행).
