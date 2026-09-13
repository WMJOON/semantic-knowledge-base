# KB 유지보수 가이드

> Ontology drift 판단의 기준은 `ontology/system/semantic/**/*.ttl`입니다. explain Markdown과
> JSON report는 파생 산출물이므로 정본 TTL을 고친 뒤 재생성합니다.

`skb-maintain`이 담당합니다. scan → analyze → rewrite → report 순서로 진행합니다.

---

## 언제 유지보수가 필요한가

| 증상 | 적용 |
|------|------|
| orphan 노드 (wikilink 0개) | `scan --check orphan` |
| 노트가 너무 길어졌다 | `scan --check length` |
| 같은 내용이 여러 곳에 흩어졌다 | `scan --check redundancy` |
| 새 evidence를 추가했는데 ontology에 미반영 | `scan --check drift` |
| KB 전체 상태 리포트가 필요하다 | `report` |

---

## 기본 명령

```bash
# 상태 스캔
skills/skb-maintain/scripts/skb-maintain scan \
  --target my-kb [--check orphan|drift|length|redundancy]

# 통계 분석
skills/skb-maintain/scripts/skb-maintain analyze --target my-kb

# rewrite (dry-run 먼저)
skills/skb-maintain/scripts/skb-maintain rewrite \
  --target my-kb --node ontology/explain/concept/ai_agent/md/concept__rlhf.md \
  --dry-run

# 리포트
skills/skb-maintain/scripts/skb-maintain report --target my-kb
```

---

## 시나리오 1: 새 evidence 추가 후 ontology 업데이트

```
1. skb-evidence collect → evidence/seeds.jsonl 갱신
2. skb-maintain scan --check drift
   → ontology 노드 중 새 evidence를 미반영한 노드 목록
3. skb-maintain rewrite --dry-run → 변경 사항 미리보기
4. skb-maintain rewrite --apply → 승인된 노드만 적용
5. memory/task-context/work-log/ 에 변경 이력 기록
```

---

## 시나리오 2: orphan 노드 연결

```
1. skb-maintain scan --check orphan
   → wikilink 0개 노드 목록
2. skb-ontology list --target my-kb → TTL registry에서 연결 후보 탐색
3. skb-ontology add --kind triple ... --apply
4. skb-ontology validate --target my-kb
5. skb-maintain scan --check orphan (재확인)
```

---

## 시나리오 3: KB 전체 상태 점검

```bash
skills/skb-maintain/scripts/skb-maintain report --target my-kb
# → report/maintenance/ 에 리포트 저장
#   - entity 수, orphan 수, drift 비율
#   - 최근 변경 이력 요약
```

---

## 거버넌스 통합

`skb-harness`가 유지보수 실행 결과를 trajectory에 기록합니다.

```
memory/task-context/work-log/        ← 단기 작업 이력
memory/task-context/decision-history/ ← 결정 사항
harness/trajectory/                  ← 5-Axis 계측값
```

위험도 High 변경은 `skb-orchestration`의 HITL 게이트를 통과해야 합니다.

| 위험도 | 처리 |
|--------|------|
| Low | 자동 반영 |
| Medium | dry-run 확인 후 적용 |
| High | HITL 승인 필수 (`skb-orchestrate cc-check`) |
