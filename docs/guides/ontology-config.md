# TTL-only 온톨로지 설정

## 정본

온톨로지 도메인 데이터의 유일한 정본은 다음 Turtle graph입니다.

```text
ontology/system/semantic/<domain>/
  <domain>.ttl
  <domain>.shapes.ttl
  <domain>.inferred.ttl
```

`<domain>.ttl`에는 TBox, RBox, ABox, registry membership, status와 PROV-O 출처가 함께
들어갑니다. `*.shapes.ttl`은 별도 검증 graph이고 `*.inferred.ttl`은 삭제 후 재생성할 수
있는 projection입니다.

`canonical_root_hub.yaml`과 `agent-context/index/index.yaml`은 repository/tool routing
설정일 수 있지만 ontology term, relation, instance 또는 provenance 정본이 될 수 없습니다.

## 최소 graph

```turtle
@prefix ex: <https://example.org/kb#> .
@prefix skb: <https://semantic-knowledge-base.dev/ontology#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix prov: <http://www.w3.org/ns/prov#> .

ex:ontology a owl:Ontology ;
  skb:declaresTerm ex:Agent .

ex:Agent a owl:Class ;
  rdfs:label "에이전트"@ko ;
  dct:identifier "agent" ;
  skb:status "accepted" ;
  prov:hadPrimarySource <https://example.org/source/agent> .
```

## 실행

```bash
skills/skb-ontology/scripts/skb-ontology validate --target .
skills/skb-ontology/scripts/skb-ontology list --target . --json
skills/skb-ontology/scripts/skb-ontology materialize --target . --domain demo --apply
```

기존 entity/relation/instance JSONL과 LinkML YAML은 migration 입력일 뿐입니다. 변환 후
TTL을 채택하면 동기화하지 말고 legacy 파일을 archive합니다.
