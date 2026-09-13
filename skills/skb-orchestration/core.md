# core — skb-orchestration

## 1. 4가지 책임

| 영역 | 모듈 |
|------|------|
| 라우터 (의도 → workflow) | `router/match_trigger.py`, `router/resolve_workflow.py`, `router/dispatch.py` |
| CC 계약 강제 | `policy/cc_check.py` |
| 5-axis gate 판정 | `policy/gate_evaluator.py`, `policy/threshold_resolver.py` |
| HITL 2-layer | `policy/hitl_router.py`, `hooks/pretool_use.py` |

## 2. 측정 vs 정책 분리

`skb-harness`는 `governance_measurement`를 emit, 본 스킬은 그 결과를 소비해 `gate_decision`을 emit.
두 이벤트는 다른 파일에 기록 (정합성 보장):

- harness: `harness/trajectory/run-<id>.jsonl`
- orchestration: `harness/trajectory/run-<id>.orchestration.jsonl`

본 스킬 trajectory에만 등장하는 필드: `gate_passed`, `next_action`, `routing_decision`, `cc_violation`, `deprecated_route`, `hooks_disabled`.

## 3. CLI

```bash
# 사용자 의도 → workflow 라우팅 + 실행
router/dispatch.py --intent "evidence 수집" --target REPO

# 직접 workflow 호출
router/dispatch.py --workflow agent-context/workflow/evidence/evidence-collection.abox.ttl --target REPO

# harness가 남긴 measurement 소비 → gate_decision 기록
policy/gate_evaluator.py --target REPO --run-id RUN_ID

# CC 계약 검증
policy/cc_check.py --target REPO
```

## 4. Exit Code 도메인 (caller-facing)

| 코드 | 의미 |
|------|------|
| 0 | 정상 + gate passed |
| 1 | CC 위반 |
| 100 | HITL pending (사용자 ack 필요) |
| 101 | gate fail, retry 불가 |
| 102 | v1-strict 모드에서 legacy 라우팅 거부 |

harness가 던지는 0/1/2/64-79와 orchestration이 던지는 100번대는 분리된 도메인.

## 5. Threshold 해결 순서

1. workflow_id override (`overrides.by_workflow_id.<id>`)
2. category override (`overrides.by_category.<category>`)
3. defaults

먼저 매칭되는 값이 그대로 적용. 다중 매칭 시 우선순위 1번이 이김.

## 6. HITL 2-layer

### Layer 1 — always_hitl
측정값과 무관하게 차단되는 단계 (예: canonical_root_hub locked 변경, dependency 변경).
이벤트: `hitl_request` + 종료코드 100.

### Layer 2 — observability-triggered
threshold 위반 시 자동 escalate. 트리거 매트릭스:

| 축 | 위반 | 트리거 reason |
|----|------|---------------|
| non-determinism | value > max | `non_determinism_high` |
| oracle | score < min | `oracle_below_threshold` |
| cost | budget breach | `cost_budget_exceeded` |
| trajectory | incomplete | `trajectory_incomplete` |

## 7. Migration mode

`pack_config.migration.mode`:

| 모드 | 동작 |
|------|------|
| compatibility | legacy 별칭 허용 + `deprecated_route` 이벤트 |
| strict-soft | legacy 허용 + warn 로그 |
| v1-strict | legacy 거부, 종료코드 102 |

## 8. PreToolUse Hook

stdin으로 PreToolUse payload 수신. always_hitl 패턴 매칭 시 stderr에 reason 출력 + exit 1로 차단.
환경변수 `MSM_HOOKS_DISABLED=1`로 우회 가능 (trajectory에 `hooks_disabled` 기록).
