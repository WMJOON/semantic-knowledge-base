# KB 구축 흐름 가이드

> v1.1.0부터 ontology 승격 결과는 canonical Turtle에 직접 기록합니다. 아래의 evidence
> JSONL은 수집 입력일 수 있지만 entity/relation/instance JSONL은 ontology 정본이 아닙니다.

v1.0.0은 3가지 evidence 수집 경로와 Top-Down / Bottom-Up 구축 전략을 지원합니다.

---

## Evidence 수집 경로

| 경로 | 언제 | 스크립트 |
|------|------|---------|
| URL / 로컬 MD | 논문·문서·웹 페이지 수집 | `skb-evidence collect` |
| Graphify ETL | 코드베이스를 KB에 수집 | `graphify_to_skb.py` |
| 수동 작성 | 직접 `evidence/seeds.jsonl`에 추가 | — |

### Graphify ETL 흐름

코드베이스를 KB evidence로 수집할 때 씁니다. `file_type == "concept"` 노드만 통과시켜 시맨틱 추상화를 유지합니다.

```
graphify .
    ↓ Step 1–2: Tree-sitter AST + LLM 시맨틱 추출
graph.json (nodes: code + concept + document)
    ↓ graphify_to_skb.py (concept 필터 + god node 탐지)
evidence/graphify/entity_candidates.jsonl   ← concept 노드만
evidence/graphify/relation_candidates.jsonl ← concept 간 엣지
    ↓ 후보 검토 + skb-ontology add --apply
ontology/system/semantic/{domain}/{domain}.ttl         ← registry/link gate 후 승격
```

---

## 전략 선택 기준

| 조건 | 전략 |
|------|------|
| 도메인 구조가 선명하고 evidence 미수집 | **Top-Down** |
| 도메인 구조 불명확하고 evidence 이미 있음 | **Bottom-Up** |
| 코드베이스 구조를 KB로 수집 | **Graphify ETL** |

---

## Top-Down Flow

구조를 먼저 설계하고 evidence를 채웁니다.

```
skb init (ontology/system/semantic 골격)
    ↓
skb-ontology add --kind class (TTL TBox 클래스 등록)
    ↓
skb-evidence collect (URL/MD → seeds)
    ↓
skb-ontology add --kind individual (TTL ABox 인스턴스 등록)
    ↓
skb-ontology validate (registry/naming/dedup/link/SHACL)
    ↓
status: draft → accepted → stable
```

---

## Bottom-Up Flow

evidence를 먼저 수집하고 구조를 귀납합니다.

```
skb-evidence collect (URL/MD → seeds)
    ↓
반복 등장 개념 추출
    ↓
skb-ontology add --kind class (TTL TBox 클래스 귀납 정의)
    ↓
skb-ontology add --kind individual/triple (TTL ABox 배치·연결)
    ↓
skb-ontology validate (registry/naming/dedup/link/SHACL)
    ↓
status 승격
```

---

## 핵심 규칙

**Rule 1. ontology ≠ evidence**
- `ontology/system/semantic/**/*.ttl` = 클래스·관계·인스턴스 정본
- `ontology/explain/**/*.md` = 사람을 위한 파생 projection
- `evidence/` = 정당화 근거 (justification)

**Rule 2. 검증 게이트**

`skb-ontology validate`는 parse → registry/link 완전성 → naming/dedup →
SHACL 순으로 실패 폐쇄형 검증을 수행합니다. 추론은 이 게이트를 통과한
그래프에서만 수행합니다.

**Rule 3. 종료 조건**
재시도 1회 후 미달이면 status를 한 단계 낮춰 기록하고 종료합니다. 루프를 계속 돌리는 것보다 낮은 status로 기록하는 편이 효율적입니다.
