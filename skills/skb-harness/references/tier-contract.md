# Tier Contract

SPEC: `skb-harness-SPEC` §6.

## 4-Tier 모델

| Tier | 이름 | 입력 | 부수효과 | 시간 budget |
|------|------|------|----------|------------|
| L0 | static | workflow TTL 또는 target path | read-only | ≤ 5s |
| L1 | fixture | fixture yaml + deterministic inputs | scratch dir만 | ≤ 30s |
| L2 | integration | 실 repo + workflow TTL | repo 파일 변경 가능 (mode=apply) | ≤ workflow.timeout_seconds |
| L3 | eval | run 결과 + fixture answer key | trajectory 분석, 리포트 | ≤ 5min |

각 tier는 **자기 충족적**이다. L0 통과는 L1을 보장하지 않는다.

## tier별 디렉토리 (실 repo)

```
harness/
├── run.sh                # thin wrapper → MSM_HARNESS_HOME/runtime/run.sh
├── tiers/
│   ├── L0_static/
│   ├── L1_fixture/
│   ├── L2_integration/
│   └── L3_eval/
├── fixtures/             # L1 입력
├── trajectory/           # 모든 run의 jsonl
├── reports/              # L3 산출
└── oracle/               # 스킬별 oracle 함수 모임
```

## 실패 처리

| Tier | 실패 시 |
|------|---------|
| L0 | exit 1, `tier_l0_fail` |
| L1 | exit 1, fixture diff를 troubleshooting/에 저장 |
| L2 | dry-run이면 plan 실패 보고, apply면 rollback 시도 후 conflict report |
| L3 | warn 또는 fail (orchestration 임계치에 위임) |
