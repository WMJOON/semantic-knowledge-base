# core — skb-maintain

## 1. 공통 프로토콜 (SCAN / REWRITE / ANALYZE / REPORT)

| 단계      | 책임                                          | 산출                                                                        |
| ------- | ------------------------------------------- | ------------------------------------------------------------------------- |
| SCAN    | asserted TTL 탐색 → drift/orphan/eval 탐지 → plan JSON 출력 | stdout plan JSON, `harness/trajectory/run-<id>.jsonl`                     |
| REWRITE | TTL 수정이 필요한 finding을 HITL로 전달 | `agent-context/work-memory/insight-record/<id>__rewrite.md` |
| ANALYZE | domain별 TTL term/relation 통계 계산 → report 저장 | stdout report, `harness/reports/maintain-analysis-<id>.md`                |
| REPORT  | trajectory 읽기 → troubleshooting 요약          | `agent-context/work-memory/insight-record/<id>__report.md`                |

## 2. CLI

```bash
# drift/orphan/eval 모두 scan (기본)
scripts/skb-maintain scan --target ./my-kb

# 특정 domain만
scripts/skb-maintain scan --target ./my-kb --domain ai-agent

# drift만
scripts/skb-maintain scan --target ./my-kb --kind drift

# dry-run rewrite (기본 — 파일 변경 없음)
scripts/skb-maintain rewrite --target ./my-kb --plan /path/to/plan.json

# rewrite 실제 적용
scripts/skb-maintain rewrite --target ./my-kb --plan /path/to/plan.json --apply

# analysis report 생성
scripts/skb-maintain analyze --target ./my-kb

# troubleshooting report
scripts/skb-maintain report --target ./my-kb --since 2026-05-01
```

## 3. Scan 종류

### drift

| 유형 | 조건 |
|------|------|
| `ttl_validation` | parse, registry/link, naming/dedup 또는 SHACL gate 실패 |

### orphan

| 유형 | 조건 |
|------|------|
| `seed_orphan` | `evidence/md/*.md`인데 seeds.jsonl에 없음 |
| `semantic_orphan` | accepted/stable registry term인데 semantic in/out relation이 없음 |

### eval

domain별 통계:
- class / property / SKOS concept / individual / semantic relation 수
- status 분포 (draft/accepted/stable/deprecated)
- evidence coverage = `prov:hadPrimarySource`가 있는 registry term 비율
- relation density = relation_count / max(entity_count, 1)

## 4. Auto-fix 경계

TTL 정본에 대한 자동 수정은 없다. 모든 structural finding은 `hitl_required`로 전달한다.

다음은 항상 `hitl_required`:
- id rename
- entity/relation 삭제
- domain 이동
- accepted+ entity에 영향 주는 rewrite

## 5. Rewrite 가드

`rewrite`는 `auto_fixes`가 있는 과거 plan을 거부한다. 승인된 수정은 `skb-ontology`로
정본 Turtle에 적용한 뒤 다시 scan한다.

## 6. 산출 위치

| 경로 | 내용 |
|------|------|
| stdout | scan plan JSON / analyze report / report text |
| `harness/trajectory/run-<id>.jsonl` | scan 이벤트 로그 |
| `harness/reports/maintain-analysis-<id>.md` | analyze report 저장 |
| `agent-context/work-memory/insight-record/<id>__rewrite.md` | rewrite 적용 로그 |
| `agent-context/work-memory/insight-record/<id>__report.md` | troubleshooting report |

## 7. Oracle — maintain_drift_readiness

| 조건 | 점수 |
|------|------|
| TTL validation failure = 0 | +0.40 |
| semantic orphan = 0 | +0.20 |
| TTL term provenance coverage ≥ 0.80 | +0.20 |
| relation density avg ≥ 0.5 | +0.10 |
| canonical_root_hub.yaml 존재 + locked=true | +0.10 |

Gate: ≥0.85 pass, ≥0.70 warn, <0.70 fail.
