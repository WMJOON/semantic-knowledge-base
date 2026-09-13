# core — skb-harness

## 1. 책임

| 영역 | 내용 |
|------|------|
| Run context slot | `.msm-context/active/<run_id>/` 생성·관리·아카이브·GC |
| Trajectory | `harness/trajectory/run-<run_id>.jsonl` append-only 기록 |
| 4-Tier runtime | L0 static / L1 fixture / L2 integration / L3 eval |
| 5-axis 계측 | non-determinism, trajectory, oracle, cost, HITL |
| Memory | task-context/work-log/<run_id>.md, ontology-index 갱신 큐 |
| Retry | workflow.governance.max_retry 한도 내 자동 재시도 |
| Oracle | workflow.governance.oracle 함수 호출·결과 기록 |

## 2. CLI

```bash
# workflow 실행
runtime/run.sh --workflow PATH --tier L0 --mode dry-run --target REPO

# skill 직접 호출 (bootstrap 등)
runtime/run.sh --skill skb-repository-setup --tier L0 --mode validate-only --target REPO

# 외부에서 run_id 주입 (pipeline child step)
runtime/run.sh --workflow PATH --tier L2 --mode apply --target REPO \
  --run-id 20260518T120000Z --parent-run-id 20260518T115959Z
```

`--workflow`와 `--skill`은 상호배타. 둘 다 없으면 exit 2.

## 3. Exit Code 도메인

| 코드 | 의미 |
|------|------|
| 0 | 정상 |
| 1 | CC 위반 / 일반 실패 |
| 2 | apply_partial (예: locked hub 변경 대기) |
| 64-79 | skill→harness retry-safe (harness가 자동 재시도) |

orchestration이 caller에게 던지는 100번대(HITL pending=100, gate fail=101, legacy reject=102)는 본 스킬 범위 밖.

## 4. Trajectory Append-Only

- 한 run = 1개 jsonl 파일
- O_APPEND write, 줄 단위 fsync (선택)
- 정정은 새 이벤트 추가로만 (truncate/rewrite 금지)

## 5. 5-Axis 측정

| 축 | 기본 동작 |
|----|----------|
| non-determinism | N=1 기본 (측정 안 함); workflow.governance.non_determinism.sample_n ≥ 2 시에만 |
| trajectory | run 종료 시 step_started ↔ step_finished 매칭 검사 |
| oracle | workflow.governance.oracle 지정 시 호출 |
| cost | step별 누적 (tokens·seconds·power_wh) |
| HITL | hitl_request/hitl_ack 이벤트 카운트 |

정책 판정은 본 스킬이 하지 않는다. `governance_measurement` 이벤트로 5축 값만 기록.

## 6. Cost Mode 자동 감지

| 조건 | mode |
|------|------|
| `OLLAMA_HOST` 도달 가능 또는 ollama MCP 응답 | `full` |
| 위 실패 | `fallback` |

`manifest.yaml.cost_mode`에 기록. workflow TTL/YAML의 override는 무시된다.

## 7. Memory 2-tier

- `agent-context/work-memory/worklog/<run_id>.md`: run 종료 시 매번 생성
- `agent-context/work-memory/{auditlog,track-record,insight-record}/`: orchestration 또는 스킬이 채움
- `agent-context/work-memory/index.md`: work-memory 인덱스

## 8. Run Context Slot 라이프사이클

```
CREATE  → .msm-context/active/<run_id>/manifest.yaml (atomic write)
APPEND  → decisions.jsonl (rename-on-write)
CLOSE   → outputs.json 확정 + work-log 생성
ARCHIVE → 7일 후 archive/<yyyy>/<mm>/<run_id>.tar.gz 이동
GC      → archive 30일 후 삭제
```

본 구현은 ARCHIVE/GC를 별도 명령(`runtime/gc.py`)으로 분리. crontab/launchd에서 호출.

## 9. 동시성

- 한 repo에 동시 active run 다수 허용
- canonical_root_hub.yaml 변경 동반 run은 1개 제한 (advisory lock: `.msm-context/active/.hub-write.lock`)
- lock 점유 시 두 번째 run은 `hitl_request: hub_write_lock_held`
