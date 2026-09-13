# Migration Guide — v0.2.0 → v0.10.0

SPEC: skb-orchestration-v0.10.0-SPEC §3, §12.

## 3-단계 마이그레이션

| 모드 | 기간 | 동작 |
|------|------|------|
| `compatibility` | 채택 ~ +90일 | v0.2.0 트리거 + v0.10.0 트리거 모두 허용. legacy 호출 시 `deprecated_route` 이벤트 |
| `strict-soft` | +90 ~ +180일 | legacy 트리거 시 warn 로그 + `deprecated_route` |
| `v1-strict` | +180일 ~ | legacy 트리거 거부 (exit 102) |

전환 시점은 자연일 기준이 아니라 **사용자 결정 시점에 `pack_config.migration.mode`를 수동 advance**한다.

## 스킬 별칭 매핑

| v0.2.0 호출 | v0.10.0 라우팅 |
|-------------|--------------|
| `msm-ralph-etl` | `skb-evidence` |
| `msm-kb-graph` (구축) | `skb-ontology` |
| `msm-kb-graph` (추론) | `skb-graph-reasoning` |
| `msm-kb-graph` (검색) | `skb-semantic-search` |
| `msm-mece-validator` | `skb-ontology` |
| `msm-kb-rewrite` | `skb-maintain` |
| `msm-data-analysis` | `skb-maintain` |
| `msm-rdf-owl-bridge` | `skb-graph-reasoning` |
| `msm-obsidian-cli` | (글로벌 유지) |

## 단계별 체크리스트

### Phase A — compatibility 진입 (즉시)
- [ ] `pack_config.json`의 `migration.mode = "compatibility"` 확인
- [ ] `skb-orchestration` v0.10.0 설치
- [ ] `skb-harness` v0.10.0 설치 (router가 dispatch할 대상)
- [ ] 기존 v0.2.0 스킬 6종은 leave-in-place

### Phase B — strict-soft 진입 (사용자 결정 시)
- [ ] `migration.mode = "strict-soft"` 변경
- [ ] 90일 활동 로그 검토: `deprecated_route` 이벤트 빈도 분석
- [ ] 도메인 스킬 v0.10.0 6종이 모두 설치됐는지 확인

### Phase C — v1-strict 진입 (사용자 결정 시)
- [ ] `migration.mode = "v1-strict"` 변경
- [ ] router-trigger-map.yaml의 `legacy_aliases` 제거
- [ ] v0.2.0 스킬 디렉토리 삭제 (별도 백업 후)

## 자주 묻는 질문

**Q1. `compatibility` 모드에서 legacy 호출을 명시적으로 거부하려면?**
A. `--strict` 플래그로 일회성 v1-strict 동작. 영구 적용은 mode 변경.

**Q2. v0.2.0과 v0.10.0 모두 설치한 상태에서 충돌이 일어나면?**
A. orchestration의 router가 항상 v0.10.0을 우선 dispatch. v0.2.0 호출은 alias로 변환된다.

**Q3. 카나리아 테스트 중에 `v1-strict`로 일부만 시험하려면?**
A. 현재는 모드가 글로벌 1개. 부분 모드는 v0.11에서 검토.
