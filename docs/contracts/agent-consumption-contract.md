# Agent Consumption Contract (v0.1 draft)

> **SKB(semantic-knowledge-base, 구 MSM)가 publish 하고 에이전트 실행 계층이 소비하는**
> knowledge artifact 계약. 첫 소비자는 MSO execution 이며, 계약 자체는 provider-neutral 하다.
> 이력: MSM v2.0.0 redirection ADR(superseded) → TOA(철회) → SKB 로 흡수 (UD-0010).
> status: draft — optimizer ContextPack 배선 PoC 결과를 반영해 v0.2 로 갱신한다.

## 당사자와 방향

```text
producer:  SKB   (skb-ontology materialize → trust gate → publish 번들)
consumer:  에이전트 실행 계층
           - MSO execution (mso-workflow-optimizer · mso-graph-observability · mso-intent-analytics)
           - control plane agent (Claude Code / Codex — human 판단 근거)
방향:      source KB ──materialize──▶ publish 번들 ──(read-only)──▶ consumer
```

- consumer 는 publish 번들을 **읽기만** 한다. 역방향 쓰기(실행 결과의 KB 반영)는
  control plane 의 HITL 경유로만 이루어진다.
- KB 내부 경로는 계약 표면이 아니다 — consumer 는 **publish 번들**만 참조한다.
- SKB 는 publish 전 trust gate(SHACL·MECE·PROV·재현성)를 통과시킬 책임을 진다.

## Expressivity Ladder — "온톨로지" 주장의 정직한 한정

SKB 는 형식 온톨로지가 아니라 **graph knowledge base** 를 기본형으로 인정한다.
번들이 달성한 표현력 수준을 manifest 에 선언하고, 그 이상을 주장하지 않는다.

| Level | 내용 | 달성 방법 | 소비자 예 |
|---|---|---|---|
| **L0** | instance graph + 라벨 | 자동 (evidence 수확) | 그래프 관측, 탐색 |
| **L1** | taxonomy (subclass 트리 · 단일 부모 · MECE) | 자동 + MECE 게이트 | ContextPack 주입, 어휘 grounding |
| **L2** | 제약 스키마 (SHACL shapes, closed-world 타입 정의) | 반자동 (shape 유도 + 검토) | 실행 시 데이터 검증 게이트 |
| **L3** | 공리화 OWL (disjointness · defined class · property chain) + 추론 | HITL 저작 (`axiom` 명령) | 추론이 필요한 workflow 만 |

- consumer 는 요구 수준을 선언한다 (예: ContextPack = L1 이상, 추론 workflow = L3).
- MECE 게이트(형제 disjoint + 전수 커버리지)는 L1→L3 승격의 씨앗이다
  (`owl:disjointWith` + covering axiom 으로 직역 가능).
- L3 는 도메인 단위 opt-in — 전 KB 공리화를 전제하지 않는다.

## Artifact 표면

publish 번들 root 기준. `{domain}` 은 KB 도메인 이름. 원본 경로는 skb-ontology 의
`ontology/system/**` 레이아웃을 따르며, manifest 에 원본→번들 매핑을 기록한다.

| # | artifact | 번들 경로 (초안) | 형식 | 최소 Level | 용도 |
|---|----------|------|------|------|------|
| A1 | Asserted semantic graph | `ontology/{domain}.ttl` | Turtle/OWL | L1 | TBox·RBox·ABox·registry·PROV 조회 |
| A2 | ABox view | A1의 `owl:NamedIndividual` subgraph | Turtle/SPARQL result | L0 | 실행 시 개체 사실 lookup |
| A3 | Inferred facts | `inferred/{domain}.inferred.ttl` | Turtle | L3 | reasoning 파생 사실 lookup |
| A4 | SHACL gate | `ontology/{domain}.shapes.ttl` | Turtle/SHACL | L0 | 근거·구조·cardinality 차단 게이트 |
| A5 | 도메인 어휘 view | A1의 registry term query | SPARQL result | L1 | intent-analytics · uug-grounding 소스 |
| A6 | Explain projection | `explain/**/*.md` | Markdown | L0 | control plane HITL 판단 근거 |
| M | Manifest | `manifest.json` | JSON | — | 입력 해시·계약 버전·**expressivity level**·게이트 기록·원본 매핑 |

## 소비 지점 (consumer 측 앵커)

- **mso-workflow-optimizer**: workflow 노드의 `x_msm` 실행 메타 → 도메인 클래스 참조.
  Vertex ContextPack 에 A1~A3 를 주입 (`--ontology <bundle-root>` 류 입력 — PoC 에서 설계).
- **mso-scaffold-design**: publish 번들을 `index.yaml` artifact source registry 에
  `local_file` source 로 등록 → workflow TTL 이 `index:<id>` 로 참조.
- **mso-intent-analytics / uug-grounding**: A5 를 멀티-레지스트리 브리지의 도메인 소스로 소비.

## 보증 (producer 의무 — trust gate)

1. **SHACL clean**: A1/A2 는 `shapes-validate` 통과 (prov shapes 자동 병합 포함).
2. **Registry clean**: A1은 naming, duplicate, completeness, link gate를 통과한다.
3. **조인 키**: A1 의 `owl:Class` 는 `dct:identifier` 를 보유해 explain record·source_refs 와 조인 가능.
4. **재현성**: A3 는 `materialize` 재실행으로 재생성 가능하며, manifest 의 입력 해시로 대조 가능.
5. **Level 정직성**: manifest 의 expressivity level 은 게이트가 실증한 수준만 기록한다.

## 버저닝

- 계약 자체: 본 문서 semver (v0.x draft → v1.0 확정). manifest 에 적용 계약 버전 명시.
- 번들: manifest 의 입력 해시 + 생성 시각. breaking 변경(번들 경로/스키마)은 계약 major bump 로만 허용.
- SKB/MSO 릴리스 결합: 계약 버전을 양측 changelog 에 명시해 호환 범위를 선언한다.

## Non-Goals

- 실행 결과의 KB 자동 반영 (control plane HITL 경유만)
- SPARQL endpoint / 실시간 inference 서비스
- MSO 내부 workflow TTL 의 스키마 규정 (mso-workflow-design 소관)
