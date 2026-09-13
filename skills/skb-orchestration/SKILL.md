---
name: skb-orchestration
description: |
  SKB v1.0.0 정책·라우팅 레이어. 사용자 의도를 워크플로우로 라우팅하고,
  CC 계약·HITL 정책·5-axis gate를 강제한다. skb-harness의 측정값을 소비해
  gate_decision을 emit. PreToolUse hook으로 위험 동작을 차단.
metadata:
  version: "1.0.0"
---

# skb-orchestration (v1.0.0)

## What

SKB의 단일 사용자 진입점. 트리거 매칭 → 워크플로우 선택 → harness 호출 → 측정값 소비 → gate 판정.
정책은 본 스킬이, 측정은 `skb-harness`가 담당 (책임 분리).

상세 동작은 [core.md](core.md).

## Entry Points

| 진입점 | 명령 |
|--------|------|
| CLI | `router/dispatch.py --intent TEXT --target REPO` |
| Gate | `policy/gate_evaluator.py --target REPO --run-id RUN_ID` |
| Hook | `hooks/pretool_use.py` (stdin payload, PreToolUse) |
| CC check | `policy/cc_check.py --target REPO` |

## Dependencies

- Python 3.10+ (stdlib only)
- `skb-harness` (run dispatch)

## Non-Goals

- 측정값 생성 → `skb-harness`
- 디렉토리 부트스트랩 → `skb-repository-setup`
- 도메인 작업 실행 → 도메인 스킬
- workflow TTL 구조 검증 (기계적) → workflow TTL/SHACL 계층. YAML은 migration layer
