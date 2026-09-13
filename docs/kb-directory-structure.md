# KnowledgeBase 디렉토리 구조 (v1.2.0)

> **MSM = Human-Agent KnowledgeBase Management System**
> 인간과 에이전트가 함께 운용하는 KnowledgeBase를 관리하는 시스템.
> 본 문서는 v1.1.0 디렉토리 룰(D-1~D-7), v1.1.1 거버넌스 오버레이, v1.2.0 MSO `agent-context/` 정렬을 기준으로 한다.

---

## 거버넌스 오버레이 (v1.1.1)

> [!important] Concept/Instance 관리 정책
> Concept은 HITL 필수, Instance는 연결 깊이에 따라 차등 자동화.

| 계층 | 관리 정책 | 자동화 |
|------|---------|--------|
| **Concept** (이론/정의, Tbox) | HITL / HITLFE 검수 필수 | ❌ 사람 승인 없이 자동 생성·수정 금지 |
| **Instance — 상위 Concept 직접 연결** | 관리 대상 (Human-supervised) | ⚠️ 수동 생성 또는 검수 후 자동화 |
| **Instance — 하위 Concept 간접 연결** | 동적 자동화 (Self-healing) | ✅ 에이전트 자율 처리 |

### 적용 예

```text
concept__statistics                          ← Concept (HITL 필수)
  └─ Has Instances (직접 연결)
      ├─ instance__descriptive-statistics    ← 관리 대상 (상위 직접)
      ├─ instance__inferential-statistics    ← 관리 대상 (상위 직접)
      └─ instance__regression-analysis       ← 관리 대상 (상위 직접)

concept__descriptive-statistics              ← 하위 Concept (HITL 필수)
  └─ Has Instances (간접 연결, 동적)
      ├─ instance__descriptive-example-1     ← 동적 자동화 (하위 간접)
      ├─ instance__descriptive-example-2     ← 동적 자동화 (하위 간접)
      └─ ...                                  ← 자동 생성 가능
```

### Why

- **Concept = 온톨로지 백본** → 실수 시 전체 구조 붕괴 → HITL 필수
- **상위 Instance** = 대표 사례 → 품질 보증 필요 → 관리 대상
- **하위 Instance** = 패턴화된 대량 사례 → 자동화 효율 우선 → 동적 처리

> [!note] Enforcement
> 정책의 자동 강제(가드, 검증)는 v1.2.0에서 `skb-ontology` HITL 가드 및 `skb-maintain` instance 티어 검증으로 구현 예정. v1.1.1은 문서화 레이어.

---

## 전체 구조 (D-7 + MSO 정렬)

```text
{kb-root}/                          ← knowledgeBase 루트
  canonical_root_hub.yaml           ← locked SSOT (도메인·경로 선언)
  ontology/
    system/                         ← 형식 그래프 (machine-readable, Turtle/RDF/OWL)
      semantic/                     ← 정적 의미 그래프 (Class/Property)
        {domain}.ttl                ← 클래스·계층·role/property 공리
        {domain}.prov.ttl           ← PROV-O 출처 그래프
        {domain}.prov.shapes.ttl    ← 출처 강제 SHACL gate
      kinetic/                      ← 작용·변환 (workflow, action)
        {domain}.ttl                ← transition/action rule graph
      dynamic/                      ← 변화·시간성 (event, state-change)
        {domain}.ttl                ← event/state/derived-value semantics
    explain/                        ← 자연어 표현 (human-readable, narrative)
      explain__class.md             ← L1 anchor
      concept/                      ← 추상 개념 (Class)
        concept__class.md           ← L2 anchor
        {cluster}/                  ← 도메인 클러스터 (L0 of explain.concept)
          {cluster}__class.md
          {entity-type}__{slug}.md  ← Class (type=concept/pattern/technique/...)
          {sub-class}/
            {sub-class}__class.md
            ...
      instance/                     ← 구체 사례 (Instance)
        instance__class.md
        {cluster}/
          {slug}__entity.md         ← 사람이 읽는 instance snapshot/projection
  evidence/                         ← 원본·seed registry (PROV-O 입력)
    seeds.jsonl                     ← source id registry (`evidence:seed:*`)
    md/                             ← source-note / chunk projection
    graphify/                       ← Graphify ETL 출력
      entity_candidates.jsonl
      relation_candidates.jsonl
  record-archive/                    ← 실제 record archive (ontology 외부)
    registry/
      instance-ids.jsonl            ← stable instance id + type/source refs
    runtime/
      runtime.db                    ← SQLite OLTP 상태 저장소
    events/
      *.jsonl                       ← append-only occurrence/change events
    derived/
      *.jsonl                       ← 도출값·materialized state records
    snapshots/
      *.parquet                     ← DuckDB/OLAP projection snapshot
  planning/                         ← 장기 태스크 계획
  report/                           ← 설명 문서·논문
  agent-context/                    ← agent-facing 운영 context (MSO 표준)
    index/
      index.yaml                    ← scaffold/index SSOT
    workflow/                       ← workflow 정의·라우팅
      index.yaml                    ← YAML edit/migration layer
      index.ttl                     ← runtime routing registry SSOT
      {category}/
        *.yaml                      ← 편집·마이그레이션 레이어
        *.abox.ttl                  ← 실행 정본 (harness/orchestration 우선 소비)
    work-memory/                    ← 작업 메모리 (MSO work-memory 표준)
      auditlog/
      worklog/
      track-record/
      insight-record/
  harness/                          ← 하네스·런타임
    run.sh
    reports/
  .claude/                          ← Claude 스킬·훅
    skills/
    hooks/
  .codex/                           ← Codex 설정·훅
    config.toml
    hooks.json
```

> [!important] Legacy path policy
> 과거 루트 `workflow/` 및 `memory/` 경로는 더 이상 정본 위치가 아니다.
> 신규·갱신 문서는 `agent-context/workflow/` 및 `agent-context/work-memory/`를 사용한다.
> 루트 `workflow/` 또는 `memory/`가 발견되면 마이그레이션 입력 또는 호환성 잔재로만 취급한다.

---

## v1.1.0 결정사항 (D-1 ~ D-7)

| D# | 결정 | 비고 |
|----|------|------|
| **D-1** | 부모 노드 명명: `{dir-name}__class.md` | `ontology/explain/` Markdown anchor 전용 |
| **D-2** | 단일 부모 원칙 | 다중 도메인 = `cross_reference` |
| **D-3** | L0~L4 권장, L5+ 자유 | L0=Canonical Cluster |
| **D-4** | 5축 분류(Model/Runtime/...) 비강제 | `--template 5axis` 옵션 |
| **D-5** | `unclassified/` 디렉토리 운영 | 분류 보류 entity |
| **D-6** | TBox/RBox/ABox = Class/Property/Instance | 의미 차원 분리, 파일명 분리 아님 |
| **D-7** | 4계층 구조 (system / explain / evidence) | MSM identity |

---

## 두 큰 분기: `system/` vs `explain/`

| 영역 | 책임 | 표현 방식 | 상태 |
|------|------|----------|------|
| **ontology/system/** | 형식 logic과 ontology domain 정본 | Turtle (`*.ttl`) / RDF / OWL | ✅ v1.1.0 canonical |
| **ontology/explain/** | 자연어 narrative projection | Markdown (frontmatter + body) | ✅ derived view |
| **evidence/** | 1차/2차 출처 자료 + PROV-O 입력 | URL, source-note, seed id | ✅ 운영 중 (기본) |

- **explain ← system**: explain은 TTL 정본에서 생성하는 단방향 projection이다.
- **ontology ↔ evidence**: 모든 개념·사례는 TTL의 `prov:hadPrimarySource` IRI로 근거를 연결한다.
- `ontology/system/`에는 Markdown anchor를 두지 않는다. 사람이 읽는 anchor와 explain projection은 `ontology/explain/`이 담당하고, `system/`은 `*.ttl` 그래프 산출물만 둔다.
- `ontology/system/semantic/*.ttl` 내부에서 TBox/RBox는 파일명이 아니라 `owl:Class`, `owl:ObjectProperty`, `rdfs:subClassOf`, `rdfs:domain/range`, `owl:propertyChainAxiom` 같은 RDF/OWL 구문으로 구분한다.
- `ontology/system/kinetic/`과 `ontology/system/dynamic/`은 실제 row/event 값을 저장하지 않는다. 변화 규칙과 상태 의미는 ontology에 두고, 실제 레코드는 `record-archive/`에 둔다.

> [!important] TTL-only 정본
> 사람은 explain projection을 우선 읽을 수 있지만 에이전트와 검증기는 항상
> `ontology/system/semantic/**/*.ttl`을 정본으로 소비한다.

---

## Evidence ↔ PROV-O 매핑

`evidence/`는 원천과 수집 기록을 보관한다. ontology term은 정본 TTL에서 evidence IRI를
`prov:hadPrimarySource`로 직접 연결한다.

| 입력/산출 | 역할 | 매핑 |
|----------|------|------|
| `evidence/seeds.jsonl` | source registry | 각 seed id는 `prov:Entity` 후보 |
| `ontology/system/semantic/{domain}/*.ttl` | ontology 정본 | term이 `prov:hadPrimarySource`를 직접 보유 |
| `ontology/system/semantic/{domain}/*.shapes.ttl` | SHACL gate | 출처 없는 registry term 차단 |
| `ontology/explain/**/*.md` | human-readable projection | TTL identifier/label/provenance를 투영 |

규칙:

- `prov:hadPrimarySource` 없는 class/property/individual은 validation failure다.
- `shapes-validate`는 같은 디렉토리의 `*.prov.*`를 병합해 출처 미상 `owl:Class`를 실패시킨다.

---

## explain의 두 분기 (D-6)

### `ontology/explain/concept/` — 추상 Class

```yaml
---
entity: concept__reinforcement-learning
type: concept            # Class의 sub-category (concept/pattern/technique/...)
cluster: technical
status: draft
relations:
  - type: belongs_to
    target: "[[reinforcement-learning__class|Reinforcement Learning Class]]"
    category_axis: cluster
---
```

prefix(`concept__`, `pattern__`, `technique__` 등)는 모두 **Class의 type-axis**.
TBox 영역의 모든 노드는 본질적으로 Class.

### `ontology/explain/instance/` — 구체 Instance

```yaml
---
entity: gpt4__entity
type: instance
type_of: "[[language-model__class|Language Model Class]]"
cluster: technical
status: experimental
source_doc_id: evidence__openai_gpt4
---
```

ABox 영역의 모든 노드는 인스턴스. `type_of` 관계로 TBox class와 연결.
단, `ontology/explain/instance/*.md`는 사람이 읽는 snapshot/projection이며, stable id·row·event의 정본 저장소가 아니다.

> ⚠️ ABox SPEC은 v1.2.0에서 확정 (OI-E).

---

## Record Archive 경계

실제 데이터는 ontology 안에 직접 누적하지 않는다.
`ontology/`는 의미 모델과 projection을 담당하고, `record-archive/`는 row·event·state의 보존·재현 가능한 append-only archive를 담당한다.

권장 이름은 `record-archive/`이다.
`data/`는 범위가 너무 넓고, `instance/`는 `ontology/explain/instance/`와 혼동되며, `data-record/`는 시간축과 보존 책임이 약하다.

| 계층 | 저장 대상 | 쓰기 성격 |
|------|----------|----------|
| `record-archive/registry/instance-ids.jsonl` | instance stable id, type, source_refs | append/update, id 정본 |
| `record-archive/runtime/runtime.db` | 현재 row/state | SQLite OLTP, WAL |
| `record-archive/events/*.jsonl` | 발생한 변화·관측·상태 전이 이벤트 | append-only |
| `record-archive/derived/*.jsonl` | 이벤트와 규칙으로 도출된 값 | materialized derived records |
| `record-archive/snapshots/*.parquet` | 분석·projection용 스냅샷 | generated OLAP artifact |
| `ontology/explain/instance/*.md` | 사람이 읽는 instance snapshot | `skb-explain` generated projection |
| `ontology/system/kinetic/{domain}.ttl` | 변화 규칙·전이·action 의미 | formal rule graph |
| `ontology/system/dynamic/{domain}.ttl` | event/state/derived-value 의미 모델 | formal state graph |

변화 처리 원칙:

- 변화가 발생하면 원본 이벤트는 `record-archive/events/*.jsonl`에 append한다.
- 어떤 변화가 어떤 조건에서 어떤 action을 유발하는지는 `ontology/system/kinetic/{domain}.ttl`에 둔다.
- 변화 후 도출된 실제 값은 `record-archive/derived/` 또는 `record-archive/runtime/runtime.db`에 저장한다.
- 도출값의 의미, 상태 타입, 이벤트 타입, 유효한 상태 전이 모델은 `ontology/system/dynamic/{domain}.ttl`에 둔다.
- `ontology/explain/instance/*.md`는 위 record archive에서 생성한 최신 설명 snapshot으로 취급한다.

---

## 시간축 정책

MSM은 단일 "실제 시간"을 강제하지 않는다.
같은 evidence나 instance도 source 관점, 수집 관점, archive 기록 관점에서 시간이 다르기 때문이다.

| 필드 | 관점 | 의미 |
|------|------|------|
| `published_at` | source time | 원천이 주장하는 발행·공개 시각. 알 수 없거나 추정일 수 있다. |
| `observed_at` | observation time | MSM이 해당 원천 내용을 처음 관측·fetch한 시각. |
| `captured_at` | capture time | PDF/PNG/HTML 등 검증 스냅샷을 박제한 시각. |
| `archived_at` | archive time | `record-archive/` 또는 `evidence/seeds.jsonl`에 레코드가 append된 시각. |
| `valid_at` / `effective_at` | domain time | 해당 fact/state가 도메인 안에서 성립한다고 보는 시각 또는 구간. |
| `derived_at` | derivation time | kinetic rule 또는 query로 도출값을 계산한 시각. |

규칙:

- `created_at`은 모호하므로 새 스키마에서는 피한다. 필요하면 `archived_at` 또는 `observed_at`으로 분해한다.
- 출처 신선도는 `observed_at`/`captured_at` 기준으로 본다.
- 원천의 시대성이나 주장의 문맥은 `published_at` 기준으로 본다.
- 상태 재현과 감사는 `archived_at` 기준으로 본다.
- 도메인 모델의 사실 유효성은 `valid_at` 또는 `effective_at` 기준으로 본다.

---

## 부모 노드 anchor 패턴 (D-1 ~ D-3)

```
{cluster}/
├── {cluster}__class.md             ← L0 (Canonical Cluster anchor)
├── concept__X.md                    ← 자식 Class (type=concept)
├── pattern__Y.md                    ← 자식 Class (type=pattern)
└── {sub-class}/                     ← 더 세분화
    ├── {sub-class}__class.md        ← L1 anchor
    └── ...
```

- **부모 anchor**: `{dir-name}__class.md`
- **자식 Class**: `{type}__{slug}.md`
- **레벨**: L0 (cluster) → L1 (sub-cluster) → ... → L4 (권장 최대) → L5+ (경고만)

---

## `unclassified/` 디렉토리 (D-5)

분류 보류 entity는 클러스터별 unclassified로 격리:

```
ontology/explain/concept/unclassified/{cluster}__unclassified.md
ontology/explain/instance/unclassified/{cluster}__unclassified.md
```

scan/validator는 정상 디렉토리로 인식하되 잔여 카운트를 리포트에 포함.

---

## ETL 흐름

```
Evidence 수집
  (skb-evidence: URL/MD → evidence/seeds.jsonl + evidence/md/)
  (graphify_to_skb.py: graph.json → entity_candidates.jsonl)
      ↓
Ontology 승격
  (skb-ontology: evidence IRI → canonical asserted TTL)
      ↓
Record archive materialization
  (stable id/row/event → record-archive/registry + runtime + events)
      ↓
Validation and inference projection
  (validate → SHACL → derived *.inferred.ttl)
      ↓
Status 승격
  draft → experimental → validated
      ↓
parent_alignment scan
  (skb-maintain: D-1~D-7 6규칙 검증)
```

---

## canonical_root_hub.yaml 스키마 (v1.1.0)

```yaml
version: "1.1"
locked: true
identity: "Human-Agent KnowledgeBase Management System"
domains:
  technical:
    concept: ontology/explain/concept/technical/
    instance: ontology/explain/instance/technical/
    semantic_graph: ontology/system/semantic/technical/**/*.ttl
  marketing:
    concept: ontology/explain/concept/marketing/
    instance: ontology/explain/instance/marketing/
system:                              # v1.2.0 formal graph layer
  semantic: ontology/system/semantic/**/*.ttl
  kinetic:  ontology/system/kinetic/**/*.ttl
  dynamic:  ontology/system/dynamic/**/*.ttl
record_archive:
  registry: record-archive/registry/**/*.jsonl
  runtime: record-archive/runtime/runtime.db
  events: record-archive/events/**/*.jsonl
  derived: record-archive/derived/**/*.jsonl
  snapshots: record-archive/snapshots/**/*.parquet
time_axes:
  source_time: published_at
  observation_time: observed_at
  capture_time: captured_at
  archive_time: archived_at
  domain_time: valid_at
  derivation_time: derived_at
provenance:
  source_registry: evidence/seeds.jsonl
  asserted_graph: ontology/system/semantic/**/*.ttl
  shapes: ontology/system/semantic/**/*.shapes.ttl
```

`locked: true`인 경우 `skb-ontology`를 통해서만 갱신 가능.

---

## v1.0.0 → v1.1.0 마이그레이션 매핑

| v1.0.0 | v1.1.0 |
|--------|--------|
| `ontology/Tbox/{cluster}/` | `ontology/explain/concept/{cluster}/` |
| `ontology/Abox/{cluster}/` | `ontology/explain/instance/{cluster}/` |
| `{name}__hub.md` | `{name}__class.md` (D-1) |
| (없음) | `ontology/system/{semantic, kinetic, dynamic}/**/*.ttl` (formal graph layer) |
| `instance/runtime.db` | `record-archive/runtime/runtime.db` |
| `instance/snapshots/` | `record-archive/snapshots/` |
| `data-record/` | `record-archive/` |
| (없음) | `unclassified/` 패턴 (D-5) |

---

## 관련 문서

- [빠른 시작](guides/quickstart.md)
- [온톨로지 설정](guides/ontology-config.md)
- [KB 구축 흐름](guides/kb-build-flows.md)
- [PRD v1.1.0](../../planning/msm_v1.1.0/msm_v1.1.0-PRD.md)
- [Parent Alignment SPEC](../../planning/msm_v1.1.0/msm-parent-alignment-SPEC.md)
