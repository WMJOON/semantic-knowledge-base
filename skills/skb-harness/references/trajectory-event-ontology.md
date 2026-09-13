# Trajectory Event Ontology

SPEC: `skb-harness-SPEC` §8.

## 공통 필드 (모든 이벤트)

```json
{
  "run_id": "20260518T120000Z",
  "ts": "2026-05-18T12:00:00.123Z",
  "event_type": "...",
  "skill": "skb-evidence",
  "workflow_id": "evidence.collection.default",
  "tier": "L0",
  "mode": "dry-run",
  "parent_run_id": null
}
```

## 이벤트 타입

| event_type | 발행 시점 | 추가 필드 |
|-----------|----------|----------|
| `run_started` | manifest 작성 직후 | `target`, `cost_mode`, `inputs_hash` |
| `step_started` | pipeline step 진입 시 | `step_id`, `tool`, `action`, `attempt` |
| `step_finished` | step 종료 시 | `step_id`, `exit_code`, `outputs_delta`, `attempt` |
| `step_aborted` | step 중단 시 | `step_id`, `reason` |
| `oracle_evaluation` | oracle 호출 후 | `oracle`, `score`, `threshold`, `passed`, `details` |
| `governance_measurement` | run_finished 직전 1회 | 5-axis 전체 |
| `hitl_request` | gate가 manual confirmation 요구 시 | `reason`, `target`, `proposed_action`, `requires_manual_confirmation: true` |
| `hitl_ack` | 사용자 승인 수용 시 | `acked_by`, `acked_at` |
| `cost_increment` | 토큰/시간/전력 누적 | `tokens_delta`, `seconds_delta`, `power_wh_delta` |
| `non_determinism_sample` | LLM N회 비교 | `n_samples`, `disagreement_ratio` |
| `tier_l0_fail` / `tier_l1_fail` / `tier_l2_fail` / `tier_l3_fail` | tier 실패 | `reason`, `fail_target` |
| `apply_partial` | mode=apply 중 일부 차단 | `blocked` |
| `ontology_index_dirty` | ontology mutation 후 | `clusters_affected` |
| `hub_write_lock_held` | advisory lock 충돌 | `lock_holder_run_id` |
| `run_finished` | 최종 정리 | `exit_code`, `duration_seconds` |

## governance_measurement 정식 스키마

```json
{
  "run_id": "...",
  "event_type": "governance_measurement",
  "non_determinism": 0.04,
  "trajectory_complete": true,
  "oracle_score": 0.92,
  "oracle_threshold": 0.85,
  "cost": {"mode": "fallback", "tokens": 1200, "seconds": 8, "power_wh": 0},
  "hitl": {"required": false, "requested": 0, "acked": 0}
}
```

**판정 필드(`gate_passed`, `escalated`, `decision`, `routed_to`)는 포함하지 않는다.** 이 필드는 orchestration mirror 파일에만 존재한다.
