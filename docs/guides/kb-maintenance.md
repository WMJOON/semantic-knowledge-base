# KB 유지보수 가이드

> Ontology drift 판단의 기준은 `ontology/system/semantic/**/*.ttl`입니다. explain Markdown과
> JSON report는 파생 산출물이므로 정본 TTL을 고친 뒤 재생성합니다.

전용 유지보수 스킬(`skb-maintain`)은 v1.3.0에서 제거됐습니다. 점검은 각 데이터의 소유 스킬이 맡고,
**수정은 항상 사람이 판단한 뒤 `skb-ontology`로** 합니다. 점검 도구는 정본을 고치지 않습니다.

---

## 증상별 점검

| 증상 | 명령 |
|------|------|
| TTL 정합(등록, 링크, 이름, 중복, SHACL) | `skb-ontology validate --target my-kb [--domain D]` |
| 어떤 관계에도 없는 accepted 용어 | `skb-ontology orphans --target my-kb [--domain D]` |
| 용어 수, status 분포, evidence 커버리지, 관계 밀도 | `skb-ontology stats --target my-kb [--domain D] [--json]` |
| 정의끼리 모순되는가 | `skb-graph-reasoning check --target my-kb` |
| seed가 가리키지 않는 evidence md 노트 | `skb-evidence verify --target my-kb --orphans` |
| 검색 인덱스가 최신인가 | `skb-semantic-search status --target my-kb` |
| Markdown 투영의 부모 노드 규칙 | `python3 skills/skb-explain/scripts/parent_alignment.py --target my-kb` |

## 권장 순서

1. `skb-ontology validate` — 실패가 있으면 다른 점검보다 먼저 고칩니다.
2. `skb-ontology orphans` / `stats` — 후보를 사람이 검토합니다(자동 수정 없음).
3. `skb-graph-reasoning check` — 모순을 확인합니다. `xsd_artifacts`는 데이터형 표기 문제이지 논리 모순이 아닙니다.
4. 수정은 `skb-ontology add` 또는 TTL 직접 편집으로 하고 1번을 다시 돌립니다.
5. 파생물 갱신: `skb-graph-reasoning reason --apply`, `skb-semantic-search index`.

## 하네스 워크플로우로 돌릴 때

`maintain` 카테고리 워크플로우(`agent-context/workflow/maintain/validation.yaml`)는 `x_msm.tool: skb-ontology`를 씁니다.
`skb-ontology/oracle/ontology_readiness.py`는 TTL 유효성, 용어 고아, evidence 커버리지, 관계 밀도, 허브 잠금을 0~1 점수로 환산하며,
워크플로우의 oracle 로 지정하면 하네스가 형제 스킬의 `oracle/` 에서 찾아 실행합니다(임계값은 워크플로우의 `oracle_threshold`).
