---
name: skb-maintain
description: |
  SKB TTL-only KB 유지보수 스킬. asserted Turtle의 drift/orphan/eval 탐지, 정합 복구 계획 생성,
  analysis report 산출, troubleshooting 기록을 담당한다.
  새 entity 생성은 하지 않는다 — 변경은 plan으로 산출 후 사용자 ack 필요.
metadata:
  version: "1.1.0"
---

# skb-maintain (v1.1.0)

## What

KB의 무결성·일관성·관측성을 점검하고 정정 계획을 생성하는 Fat Skill.

책임:
1. **scan**: drift / orphan / inconsistency 탐지
2. **rewrite**: TTL 변경이 필요하면 HITL 계획만 생성; 정본을 자동 수정하지 않음
3. **analysis**: TTL term/relation 통계, evidence 커버리지, status 분포
4. **report**: 결과를 `agent-context/work-memory/insight-record/` 및 `harness/reports/`에 기록

자세한 동작은 [core.md](core.md) 참조.

## Entry Points

| 진입점 | 명령 |
|--------|------|
| CLI — scan | `scripts/skb-maintain scan --target REPO [--domain NAME] [--kind drift|orphan|eval|all]` |
| CLI — rewrite | `scripts/skb-maintain rewrite --target REPO --plan PATH [--apply]` |
| CLI — analyze | `scripts/skb-maintain analyze --target REPO [--domain NAME]` |
| CLI — report | `scripts/skb-maintain report --target REPO --since YYYY-MM-DD` |
| Harness | `harness/run.sh --skill skb-maintain --tier L0 --mode validate-only --target REPO` |

## Triggers

- "drift 탐지", "orphan 탐지", "KB 정리"
- "KB 무결성 검사", "maintenance scan"
- "skb-maintain scan", "skb maintain"

## Dependencies

- Python 3.10+, `rdflib>=7.0`
- Bash (CLI wrapper, harness)

## Non-Goals

- entity 생성 → `skb-ontology`
- evidence 수집 → `skb-evidence`
- graph 추론 → `skb-graph-reasoning`
- 검색 인덱스 갱신 → `skb-semantic-search`
- 자동 ID rename (HITL 필요)
