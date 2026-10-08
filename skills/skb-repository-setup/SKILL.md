---
name: skb-repository-setup
description: |
  SKB v1.2.0 Fat Skill — 신규 KB 프로젝트를 TTL-only 5-Layer 구조로 부트스트랩한다.
  canonical_root_hub.yaml, ontology/system TTL, ontology/explain MD, evidence, record-archive,
  agent-context/workflow, agent-context/work-memory, harness/docs 골격을 생성한다.
metadata:
  version: "1.2.0"
---

# skb-repository-setup (v1.2.0)

## What

신규 KB를 SKB v1.1.0의 TTL-only 5-Layer 토폴로지로 부트스트랩하는 Fat Skill.
실제 entity/relation/instance/evidence 내용은 만들지 않는다 — 골격, 템플릿, 계약만 채운다.
도메인 ontology의 최초 정본은 `ontology/semantic/<domain>/<domain>.ttl`로 생성한다(`--layout legacy`는 이전 배치 `ontology/system/semantic/`).

## 배치 (`--layout`)

| 값 | 의미 |
|---|---|
| `b1` (기본) | `ontology/semantic/`, `evidence/{artifact/raw,chunk,catalog}`. 정본은 계속 TTL이다. `canonical_root_hub.yaml`의 `layout:` 섹션이 이 경로를 선언하고, 모든 skb 스킬이 그 섹션으로 경로를 찾는다. 워크플로우는 TTL(`wf:`/`skbx:`)만 만들고 `agent-context/index/artifacts.abox.ttl`(artifact 레지스트리)와 `.gitignore`(원문·파생물·실행 기록 제외)를 함께 만든다. 이미 있는 `.gitignore`는 건드리지 않는다. |
| `legacy` | `layout:` 없는 이전 배치(YAML 워크플로우, `ontology/system/semantic`, `evidence/{md,raw}`). 기존 KB와 같다. |

`layout:`이 없는 기존 KB는 스킬이 이전과 같은 경로를 쓴다(바이트 단위로 같다). 정적 점검(`validate_workflows.py`)은 모든 `skbx:tool`이 `harness/run.sh`를 가진 실제 스킬이고 모든 oracle이 실제 파일인지 확인한다.

`init --apply` 완료 시 `index.yaml`을 자동 생성·갱신한다.

자세한 동작은 [core.md](core.md) 참조.

## Entry Points

| 진입점 | 명령 |
|--------|------|
| CLI | `scripts/skb init [options]` |
| index.yaml 단독 생성 | `python scripts/gen_index.py --target PATH [--name NAME] [--domain DOMAIN]` |
| Harness | `harness/run.sh --skill skb-repository-setup --tier L0 --mode validate-only --target PATH` |

## index.yaml 자동 생성 규칙

`apply_init.py`가 init 완료 후 `gen_index.py`를 호출한다.

| 상태 | 동작 |
|------|------|
| `index.yaml` 없음 | SKB 표준 모듈 포함 신규 생성 |
| `index.yaml` 있음 + `x_msm_generated` 마커 | SKB 모듈(`skb-record-archive`, `skb-ontology-layer`) 병합, 기존 모듈 보존 |
| `index.yaml` 있음 + 마커 없음 | skip (사용자 관리 파일 — HITL 정책 준수) |

생성된 `index.yaml`은 `sf_node.py validate`로 자동 검증 가능:
```bash
python sf_node.py validate index.yaml
```

## Triggers

- "skb init", "이 KB 부트스트랩", "5-Layer 스캐폴드 생성"
- "canonical_root_hub.yaml 만들어줘"
- "SKB TTL-only repository 구조"
- "index.yaml 자동 생성"

## Dependencies

- Python 3.10+
- `pyyaml>=6.0` (gen_index.py용 — 없으면 index.yaml 생성 건너뜀)
- Bash (CLI wrapper, harness stub)

## Non-Goals

- entity/relation 생성 → `skb-ontology`
- evidence 수집 → `skb-evidence`
- full harness runtime → `skb-harness`
- HITL gate 판정 → `skb-orchestration`
- index.yaml의 사용자 모듈 자동 추가 (사용자가 직접 편집)
