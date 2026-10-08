---
name: skb-harness
description: |
  SKB v1.0.0 측정·저장 레이어. 4-Tier 런타임(L0~L3), run context slot 운영,
  trajectory event ontology 기록, 5-axis 계측, memory 2-tier 운영을 담당한다.
  정책 판정은 하지 않는다 (skb-orchestration 책임).
metadata:
  version: "1.1.0"
---

# skb-harness (v1.0.0)

## What

`harness/run.sh` 본체. workflow TTL(또는 legacy YAML) 또는 skill 진입점을 받아 4-Tier 모델로 실행하고,
모든 측정값을 `harness/trajectory/run-<id>.jsonl`에 append-only로 기록한다.
정책 판정은 하지 않는다.

자세한 동작은 [core.md](core.md).

## Entry Points

| 진입점 | 명령 |
|--------|------|
| Harness | `runtime/run.sh --workflow PATH --tier L0 --mode dry-run --target REPO` |
| Skill-direct | `runtime/run.sh --skill NAME --tier L0 --mode validate-only --target REPO` |

## Dependencies

- Python 3.10+
- stdlib only (yaml/jsonschema 미사용; 텍스트 기반)
- Bash

## Oracle and skill discovery

- Oracles are looked up in order: `<repo>/harness/oracle/<name>.py`, `skb-harness/oracle/<name>.py`, then `<skills>/*/oracle/<name>.py`
  (oracles shipped by sibling skills, e.g. `skb-ontology/oracle/ontology_readiness.py`, `skb-evidence/oracle/evidence_seed_readiness.py`).
  The loader passes only the arguments the function accepts (`evaluate(target, run_context=None, ...)`).
- An oracle that cannot be found still returns the benign `score 1.0`, but the result now carries
  `details.warning`/`details.searched` so a vacuous PASS is visible in the trajectory.
- Skills are located by `SKB_SKILL_<NAME>_HOME` (legacy alias `MSM_SKILL_<NAME>_HOME`), then as siblings of `skb-harness`,
  then in `~/.claude/skills`, `~/.agents/skills`, `~/.gemini/config/skills`, and finally `~/.skill-modules/msm-skills`.

## Non-Goals

- 게이트 통과 여부 판정 → `skb-orchestration`
- HITL 승인 → `skb-orchestration`
- 워크플로우 라우팅 → `skb-orchestration`
- 디렉토리 부트스트랩 → `skb-repository-setup`
