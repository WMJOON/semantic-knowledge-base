# Cost Mode Detection

SPEC: `skb-harness-SPEC` §7.3.

## 감지 알고리즘

```
1. OLLAMA_HOST 환경변수 또는 기본 http://127.0.0.1:11434 에 GET /api/tags 시도 (timeout 1s)
2. 200 응답 → mode=full
3. 그 외 (connection refused, timeout, 4xx/5xx) → mode=fallback
```

## power_wh 계산

- `full` mode: `references/power_wh_per_token.yaml`의 모델별 평균값 사용
  - 토큰 수 × per_token_wh
  - 알 수 없는 모델은 default 항목 사용
- `fallback` mode: 항상 0

## workflow override 금지

`workflow.governance.cost_mode` 같은 override 시도는 무시되고 자동 감지값이 우선한다 (통합 SPEC §7.2).

이유: cost mode는 환경 종속(hardware-level) 측정이므로 workflow가 거짓 보고를 할 여지를 차단한다.

## 기록 위치

- `.msm-context/active/<run_id>/manifest.yaml`의 `cost_mode` 필드
- `governance_measurement` 이벤트의 `cost.mode` 필드
