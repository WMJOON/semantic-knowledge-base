# 스킬 구성 (v1.0.0)

MSM v1.0.0은 6개 스킬이 5-Layer에서 협업합니다. `skb-orchestration`이 진입점이며, 서브스킬은 `workflow/*.yaml`을 통해 on-demand로 실행됩니다.

---

## Layer 1 — Repository Setup

### `skb-repository-setup`

**무엇을 하나:** 5-Layer KB 디렉토리 골격을 부트스트랩합니다. `canonical_root_hub.yaml` · `ontology/explain/concept/` · `ontology/explain/instance/` · `evidence/` · `workflow/` · `memory/` · `harness/`를 한 번에 생성합니다.

**이런 상황에서 쓰세요:**
- "새 KB를 처음 만들려는데 폴더 구조를 잡아줘"
- "msm v1.0.0 표준 구조로 레포를 초기화해줘"

```bash
skills/skb-repository-setup/scripts/skb init \
  --target my-kb --domain ai_agent --apply --yes
```

→ [SKILL.md](../skills/skb-repository-setup/SKILL.md) · [core.md](../skills/skb-repository-setup/core.md)

---

## Layer 2 — Workflow Skills

### `skb-evidence`

**무엇을 하나:** 외부 원본을 KB evidence로 수집합니다. URL/로컬 MD는 청킹·dedup 후 `evidence/seeds.jsonl`로 등록하고, Graphify `graph.json`은 `graphify_to_skb.py`로 concept 노드만 추출해 `evidence/graphify/`로 변환합니다.

**이런 상황에서 쓰세요:**
- "이 URL에서 evidence를 수집해줘"
- "graphify로 코드베이스를 분석하고 KB에 넣어줘"
- "로컬 논문 PDF를 seed로 등록해줘"

```bash
# URL / 로컬 MD 수집
skills/skb-evidence/scripts/skb-evidence collect \
  --target my-kb --source https://example.com/paper --apply

# Graphify ETL (코드베이스 → concept 노드)
graphify .
python skills/skb-evidence/scripts/graphify_to_skb.py \
  graphify-out/graph.json --output-dir my-kb/evidence/graphify/

# seed 목록 확인
skills/skb-evidence/scripts/skb-evidence list --target my-kb
```

| 소스 타입 | 스크립트 | 출력 |
|---------|---------|------|
| URL / 로컬 MD | `skb-evidence collect` | `evidence/seeds.jsonl`, `evidence/md/` |
| Graphify `graph.json` | `graphify_to_skb.py` | `evidence/graphify/entity_candidates.jsonl` |

→ [SKILL.md](../skills/skb-evidence/SKILL.md) · [workflow](../workflow/evidence/)

---

### `skb-ontology`

**무엇을 하나:** evidence IRI를 근거로 class·property·individual·assertion을 canonical Turtle에 직접 등록하고 registry, naming, duplicate, link, SHACL gate를 검증합니다.

**이런 상황에서 쓰세요:**
- "evidence를 ontology 노드로 승격시켜줘"
- "온톨로지 MECE 검증해줘"
- "entity 추가하고 relation 연결해줘"

```bash
# class 추가
skills/skb-ontology/scripts/skb-ontology add \
  --target my-kb --domain ai-agent --kind class \
  --iri https://example.org/kb#ReinforcementLearning --label "Reinforcement Learning" \
  --evidence https://example.org/source/rl --apply

# TTL graph 검증
skills/skb-ontology/scripts/skb-ontology validate --target my-kb --domain ai-agent

# entity 목록
skills/skb-ontology/scripts/skb-ontology list --target my-kb
```

→ [SKILL.md](../skills/skb-ontology/SKILL.md) · [core.md](../skills/skb-ontology/references/core.md)

---

### `skb-maintain`

**무엇을 하나:** KB 상태를 유지합니다. orphan 탐지·drift 평가·rewrite·통계 분석을 담당합니다.

**이런 상황에서 쓰세요:**
- "KB orphan 노드 찾아줘"
- "노트 품질이 낮아진 것 같은데 점검해줘"
- "KB 상태 리포트 생성해줘"

```bash
# 상태 스캔
skills/skb-maintain/scripts/skb-maintain scan --target my-kb

# 통계 분석
skills/skb-maintain/scripts/skb-maintain analyze --target my-kb

# 리포트
skills/skb-maintain/scripts/skb-maintain report --target my-kb
```

→ [SKILL.md](../skills/skb-maintain/SKILL.md) · [core.md](../skills/skb-maintain/core.md)

---

## Layer 3+5 — Infrastructure Skills

### `skb-harness`

**무엇을 하나:** 측정·저장 레이어입니다. memory 2-tier 운영, L0~L3 런타임 라우팅, 5-Axis(비결정성·궤적·오라클·비용·HITL) 계측을 담당합니다.

**이런 상황에서 쓰세요:**
- 직접 호출하지 않습니다 — `skb-orchestration`이 내부적으로 사용합니다.
- trajectory 로그 확인, memory tier 관리가 필요할 때

→ [SKILL.md](../skills/skb-harness/SKILL.md) · [references/](../skills/skb-harness/references/)

---

### `skb-orchestration`

**무엇을 하나:** 규범·정책 레이어이자 진입점입니다. 자연어 인텐트 → workflow yaml 라우팅, CC 계약 확인, HITL 2층 정책, 5-Axis 임계치 판정을 담당합니다.

**이런 상황에서 쓰세요:**
- 자연어로 MSM에 요청할 때 (라우터가 적합한 스킬로 연결)
- 거버넌스 정책 확인이 필요할 때

```bash
# 자연어 라우팅
skills/skb-orchestration/skb-orchestrate run \
  --intent "evidence 수집 후 ontology 반영해줘" \
  --target my-kb --tier L0 --mode dry-run

# CC 계약 확인
skills/skb-orchestration/skb-orchestrate cc-check --target my-kb

# 5-Axis 임계치 확인
skills/skb-orchestration/skb-orchestrate thresholds --category ontology
```

→ [SKILL.md](../skills/skb-orchestration/SKILL.md) · [references/](../skills/skb-orchestration/references/)

---

## 스킬 레퍼런스

| 스킬 | SKILL.md | 주요 참조 |
|------|---------|---------|
| `skb-repository-setup` | [SKILL.md](../skills/skb-repository-setup/SKILL.md) | [references/scaffold-tree.md](../skills/skb-repository-setup/references/scaffold-tree.md) |
| `skb-evidence` | [SKILL.md](../skills/skb-evidence/SKILL.md) | [workflow/evidence/](../workflow/evidence/) |
| `skb-ontology` | [SKILL.md](../skills/skb-ontology/SKILL.md) | [core.md](../skills/skb-ontology/core.md) |
| `skb-maintain` | [SKILL.md](../skills/skb-maintain/SKILL.md) | [core.md](../skills/skb-maintain/core.md) |
| `skb-harness` | [SKILL.md](../skills/skb-harness/SKILL.md) | [references/tier-contract.md](../skills/skb-harness/references/tier-contract.md) |
| `skb-orchestration` | [SKILL.md](../skills/skb-orchestration/SKILL.md) | [references/router-trigger-map.yaml](../skills/skb-orchestration/references/router-trigger-map.yaml) |

> **v1.x 예정:** `msm-graph-reasoning` (multi-hop·BFS·GraphRAG·RDF/OWL), `msm-semantic-search` (zvec·RRF)
