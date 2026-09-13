# core — skb-repository-setup

## 1. 공통 프로토콜 (DESIGN / EXECUTE / EVALUATE)

| 단계 | 책임 | 산출 |
|------|------|------|
| DESIGN | 입력·옵션 검토, 충돌 후보 식별 | plan JSON (`plan_init.py`) |
| EXECUTE | dry-run / apply / validate-only 분기 | 디렉토리·파일 생성, trajectory log |
| EVALUATE | readiness score, gate, next action | `repository_setup_readiness` 이벤트 |

## 2. CLI

```bash
# dry-run (default)
scripts/skb init --target ./my-kb

# 실제 생성
scripts/skb init --target ./my-kb --apply --yes

# domain 초기화
scripts/skb init --target ./my-kb --domain ai_agent --apply --yes

# 기존 repo 검증
scripts/skb init --target ./my-kb --validate-only
```

옵션 전체 목록: `scripts/skb --help`.

## 3. HITL 정책 (SPEC §9)

Always HITL:
- non-generated 파일 overwrite 시도
- locked `canonical_root_hub.yaml`의 domain 추가/제거
- broken symlink 교체
- `--with-venv` 기존 .venv 변경
- `--with-skill-links`가 기존 실디렉토리와 충돌

No HITL:
- 빈 디렉토리 생성
- 누락 template 파일 생성
- dry-run, validate-only

HITL 요구 시 trajectory에 `event_type: hitl_request, requires_manual_confirmation: true` 이벤트가 기록되고 apply는 exit 1 (conflict)/2 (locked hub) 로 종료된다. `--yes`로 사용자 ack를 표시한다.

## 4. Generated Marker (SPEC §10.2)

| 파일 종류 | Marker |
|----------|--------|
| Markdown | `<!-- msm:generated:file skill="skb-repository-setup" version="1.0.0" -->` |
| YAML | `x_msm_generated: { skill, version }` |
| Shell | `# msm:generated:file ...` |
| Turtle | marker 없음; 존재하는 graph는 덮어쓰지 않음 |

idempotent 재실행은 marker가 있는 파일은 keep, 없으면 conflict로 처리한다.

## 5. Readiness 가중치 (SPEC §8.2)

| 항목 | 가중치 |
|------|--------|
| 5-Layer directories present | 0.20 |
| canonical hub valid | 0.20 |
| workflow templates valid | 0.15 |
| memory/harness skeleton valid | 0.15 |
| docs/index present | 0.10 |
| skill links valid or skipped | 0.10 |
| no unresolved conflicts | 0.10 |

Gate: `>=0.85 pass`, `0.70~0.85 warn`, `<0.70 fail`.

## 6. 산출 위치

| 경로 | 내용 |
|------|------|
| `<target>/canonical_root_hub.yaml` | locked SSOT |
| `<target>/ontology/system/semantic/<domain>/<domain>.ttl` | asserted ontology SSOT |
| `<target>/agent-context/workflow/{index.yaml,evidence/,ontology/,maintain/,explorer/}` | MSO canonical workflow yaml migration layer |
| `<target>/record-archive/{registry,runtime,events,derived,snapshots,schema}` | record archive |
| `<target>/agent-context/work-memory/{auditlog,worklog,track-record,insight-record,index.md}` | MSO work-memory |
| `<target>/harness/{run.sh, tiers/, trajectory/}` | 하네스 stub |
| `<target>/docs/index.md` | 사람용 진입점 |
| `<target>/.claude/skills`, `<target>/.codex/skills` | 스킬 install 슬롯 |

## 7. Open Items

`skb-repository-setup-SPEC §13` 참조 (full harness 교체, pack_config 최종 schema, hook PreToolUse 통합 등).
