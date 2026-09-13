# 워크플로우 가이드

워크플로우 정본은 MSO 기준에 맞춰 `agent-context/workflow/{category}/*.abox.ttl`에 둔다.
기존 `*.yaml`은 `agent-context/workflow/{category}/*.yaml` 편집·마이그레이션 레이어로 유지하며,
`migrate_workflows_to_ttl.py`로 sibling ABox TTL을 생성한다.

---

## 워크플로우 카테고리

| 카테고리 | ABox TTL 위치 | 담당 스킬 |
|---------|----------|---------|
| evidence | `agent-context/workflow/evidence/` | `skb-evidence` |
| ontology | `agent-context/workflow/ontology/` | `skb-ontology` |
| maintain | `agent-context/workflow/maintain/` | `skb-maintain` |
| explorer | `agent-context/workflow/explorer/` | `msm-graph-reasoning` (v1.x 예정) |

---

## Workflow A — 새 KB 부트스트랩

```bash
skills/skb-repository-setup/scripts/skb init \
  --target my-kb --domain ai_agent --apply --yes

# canonical_root_hub.yaml + 5-Layer 골격 생성
# skb-orchestration이 agent-context/workflow/index.ttl을 우선 사용한다(index.yaml은 migration layer)
```

→ [quickstart.md](quickstart.md)

---

## Workflow B — Evidence 수집

```bash
# agent-context/workflow/evidence/evidence-collection.abox.ttl 소비
skills/skb-orchestration/skb-orchestrate run \
  --workflow agent-context/workflow/evidence/evidence-collection.abox.ttl \
  --target my-kb --tier L1 --mode dry-run
```

또는 직접 호출:

```bash
skills/skb-evidence/scripts/skb-evidence collect \
  --target my-kb --source https://arxiv.org/abs/2310.01848 --apply
```

---

## Workflow C — Graphify ETL

코드베이스를 KB evidence로 수집합니다.

```bash
# agent-context/workflow/evidence/graphify-etl.abox.ttl 소비
skills/skb-orchestration/skb-orchestrate run \
  --workflow agent-context/workflow/evidence/graphify-etl.abox.ttl \
  --target my-kb \
  --inputs '{"graph_json": "graphify-out/graph.json"}' \
  --tier L1 --mode dry-run
```

또는 직접 호출:

```bash
graphify .
python skills/skb-evidence/scripts/graphify_to_skb.py \
  graphify-out/graph.json --output-dir my-kb/evidence/graphify/
```

---

## Workflow D — Ontology 구축

```bash
# agent-context/workflow/ontology/ontology-construction.abox.ttl 소비
skills/skb-orchestration/skb-orchestrate run \
  --workflow agent-context/workflow/ontology/ontology-construction.abox.ttl \
  --target my-kb --tier L1 --mode dry-run
```

또는 직접 호출:

```bash
skills/skb-ontology/scripts/skb-ontology add \
  --target my-kb --domain ai-agent --kind class \
  --iri https://example.org/ai#Rlhf --label "RLHF" \
  --evidence https://example.org/source/rlhf --apply

skills/skb-ontology/scripts/skb-ontology validate \
  --target my-kb --domain ai-agent
```

---

## Workflow E — KB 유지보수

```bash
# agent-context/workflow/maintain/validation.abox.ttl 소비
skills/skb-orchestration/skb-orchestrate run \
  --workflow agent-context/workflow/maintain/validation.abox.ttl \
  --target my-kb --tier L1 --mode dry-run
```

또는 직접 호출:

```bash
skills/skb-maintain/scripts/skb-maintain scan --target my-kb
skills/skb-maintain/scripts/skb-maintain report --target my-kb
```

---

## 자연어 라우팅

`skb-orchestration`이 자연어 인텐트를 workflow TTL로 자동 매핑합니다.
`agent-context/workflow/index.ttl`이 있으면 우선 사용하고, 없을 때만 legacy `workflow/index.*`로 fallback한다.

```bash
skills/skb-orchestration/skb-orchestrate run \
  --intent "graphify로 이 레포 분석해서 KB에 넣어줘" \
  --target my-kb --tier L0 --mode dry-run
```

라우팅 규칙: [skills/skb-orchestration/references/router-trigger-map.yaml](../../skills/skb-orchestration/references/router-trigger-map.yaml)

### Legacy workflow YAML → TTL 마이그레이션

```bash
python skills/skb-orchestration/router/migrate_workflows_to_ttl.py agent-context/workflow
python skills/skb-orchestration/router/migrate_workflows_to_ttl.py agent-context/workflow --check
```

이 절은 workflow definition의 일회성 migration에만 해당한다. ontology domain data는
`ontology/system/semantic/**/*.ttl`만 정본이며 YAML 동기화 경로를 두지 않는다.

---

## ollama_mcp 연동

반복적·저비용 작업을 로컬 모델에 위임해 Claude 토큰을 절약합니다.

| 작업 | 위임 여부 |
|------|---------|
| evidence 청킹·요약 | ✓ ollama |
| concept 추출 초안 | ✓ ollama |
| MECE 판단·semantic bias 검출 | ✗ Claude 직접 |
