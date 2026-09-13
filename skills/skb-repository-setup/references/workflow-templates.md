# Workflow Templates

## 포맷 — MSO 구조 baseline + `x_msm` 실행 확장 (UD-0004)

MSM workflow 는 MSO `mso-workflow-design` 을 **구조 기준**으로 소비한다. 한 파일이
두 레이어를 담는다:

| 레이어 | 키 | 누가 보나 | 검증 |
|--------|----|----------|------|
| 구조(무엇을·어떤 순서로) | `module:` + named phase(step `label`/`instruction`/`directories`/decision) | MSO | `wf_node`(schema) + `wf_to_ttl`(SHACL/DAG) |
| 실행 계약 | `x_msm:` (`category`/`kind`/`mode`/`tool`·`pipeline`/`inputs`/`outputs`/`runtime`/`governance`) | skb-harness | `validate_workflows.py` |

`x_msm` 은 OpenAPI `x-` 확장 패턴이라 MSO 의 `wf_node`/`wf_to_ttl` 가 phase 가 아닌
확장 네임스페이스로 무시한다. 역으로 skb-harness 파서(`workflow_parser`·
`workflow_meta`)는 `x_msm` 에서 실행 필드를, `module` 에서 identity(`id`/`version`)를
읽는다.

레퍼런스 변환: `agent-context/workflow/evidence/graphify-etl.yaml` (git-tracked, 위 포맷 준수).
`templates/agent-context/workflow/` 4종(evidence-collection/ontology-construction/validation/
search-reason)은 repository-test 의 미변환 skeleton 이다 — 사용 시 위 포맷으로
변환 후 `wf_node`+`wf_to_ttl`+`validate_workflows.py` 통과를 확인할 것.

## 검증 키

`validate_workflows.py` 가 포맷을 자동 분기(`module:`/`x_msm:` 존재 → 레이어드)해 강제:

**레이어드(현행)** — `x_msm:` 블록:
- 필수 키: `kind`, `mode`, `governance`
- governance: `hitl_required`, `max_retry`
- mode: `dry-run` / `apply` / `validate-only`
- kind: `single` (→ `x_msm.tool` 필수) / `pipeline` (→ `x_msm.pipeline:` 블록 필수)
- 구조: MSO `wf_node`+`wf_to_ttl` 위임. MSO 부재(단독 클론) 시 위임 degrade,
  `x_msm` 검사는 그대로 실행.

**레거시 flat(후방호환)** — 모든 필드 top-level:
- top-level: `version`, `id`, `category`, `kind`, `mode`, `inputs`, `outputs`, `runtime`, `governance`
- governance: `hitl_required`, `max_retry`
- mode/kind enum 은 레이어드와 동일.

`agent-context/workflow/index.yaml` 은 워크플로를 registry 로 모은다(SPEC §6.2). full-run 검증은
`index.yaml` 필요, 단일 파일은 `--workflow PATH` 로 검증(index 불요).
