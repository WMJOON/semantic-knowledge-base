# 제안: 저자 귀속 `resolved` 경로 (신원 해소 HITL)

status: **승인(2026-10-06, 권장안 5건) · 구현 완료** — 결과는 §11 · 선행: `2026-10-06-source-agents-port.md`(구현 완료) · 대상: `skb-evidence`, `skb-ontology/references/domains/source-agents`

## 1. 문제

카탈로그의 `ec:authorshipState`는 `resolved|partial|unresolved` 세 값을 허용하지만, 지금 `resolved`를 만드는 경로가 없다. 현재 값의 실제 의미는 이렇다.

| 값 | 현재 의미 | 비고 |
|---|---|---|
| `unresolved` | 선언된 저자가 없음 (+ 사유 코드) | |
| `partial` | 저자 이름이 선언됨 (신원은 미해소) | 이름만 있어도 partial |
| `resolved` | **만드는 경로 없음** | |

`resolved`를 "저자가 누구인지 확인됐다"로 정의하려면 사람이 검토한 `MentionIdentification`이 필요하다. source-agents 모델이 이미 규칙을 갖고 있다: accepted 식별은 `reviewedBy`(사람)와 충분한 근거(강한 방법 1개 또는 서로 다른 방법 2개)가 필요하고, `Person`은 강하거나 중간 근거의 accepted 식별이 있을 때만 만든다. 모자란 것은 **후보를 모으고, 사람이 결정하고, 그 결과를 카탈로그에 되돌려 싣는 절차**다.

## 2. 기대치 (먼저 밝혀 둔다)

consumer KB 실데이터(register dry-run, 문서 566개)의 구성: 언급 3,298개, 계정 76개. 대부분의 저자는 **이름만 있는 언급**(논문 저자)이고 계정이 붙은 것은 소수다. 이름만으로는 강한 근거가 없으므로(자기 소개·이름 일치는 약한 근거) **자동으로 해소되는 양은 0이고, 해소는 사람이 근거를 가져온 건에 한한다.** `resolved`의 비율은 낮게 유지되며, 이는 "부분 커버 허용" 원칙과 맞다. 이 절차의 목표는 해소율이 아니라 **해소된 것의 근거가 감사 가능하다**는 것이다.

## 3. 상태의 재정의 (하위 호환)

값은 그대로 두고 의미와 계산식을 고정한다. 기존 카탈로그(`partial` = 이름 선언)는 그대로 유효하다.

```
저자 언급 M = 문서의 sa:AgentMention 중 mentionRole = author
M 이 해소됨 = accepted 인 MentionIdentification 이 (그 mention) 또는 (그 mention 의 observedAccount)를 가리킴
unresolved : |M| = 0                        (사유 코드 필수, 현행 유지)
partial    : |M| ≥ 1 이고 해소된 M < |M|    (현행 유지, 해소 0개 포함)
resolved   : |M| ≥ 1 이고 모든 M 이 해소됨
```

세분화는 **개수**로 한다(상태를 늘리지 않는다): `ec:authorMentionCount`, `ec:authorResolvedCount`.
저장하지 않는 파생값 원칙에 따라, 상태와 개수는 **카탈로그 빌더가 등록·식별에서 계산해 싣는 투영**이고, `catalog-validate`가 "저장된 상태 = 다시 계산한 상태"를 게이트한다(불일치 = 실패). 사람이 TTL을 손으로 `resolved`로 고쳐도 통과하지 못한다.

## 4. 절차: 제안 → 사람 결정 → 적용

```
register (구현 완료)        evidence/registrations/*.ttl      관찰: AgentMention, Account
   │
identity propose  ──────►  evidence/identity/review-queue.jsonl   (결정적 후보, 모델 없음)
   │                         사람이 편집: decision, method, evidence, identity
identity apply   ◄──────  evidence/identity/decisions.jsonl     (사람이 쓴 결정만 읽음)
   │
   ▼
evidence/identity/*.ttl    Person/Organization, MentionIdentification   (SHACL 게이트 통과 시에만 씀)
   │
catalog --apply            ec:authorshipState/Count 재계산
```

**`identity propose`(결정적, 쓰기는 큐 파일뿐)**
- 후보 단위: 계정이 있으면 **Account 1개**(그 계정을 관찰한 모든 mention이 한 번에 해소됨), 없으면 **(declaredName, declaredAffiliation) 군집**. 군집은 *제안*일 뿐 자동 병합하지 않는다. 같은 이름이 다른 사람일 수 있다.
- 큐 행: 대상 IRI들, 영향 문서 수(검토 우선순위), 이미 가진 근거 힌트(`platformVerified`, 선언된 소속, 계정 유형), 사유("이름만 있음" 등). 힌트는 *근거가 아니라 단서*다.
- 모델 호출·네트워크 조회 없음. 신원 단서를 외부에서 찾는 일(OpenAlex·ORCID 조회 등)은 사람이 하거나, 별도 승인된 조회 도구가 `identificationEvidence` IRI를 가져온다.

**`identity apply`**
- 읽는 것: `decisions.jsonl`의 항목만. 항목 = `{target, decision: accept|reject, identity: {kind: Person|Organization, slug}, methods: [...], evidence: [IRI...], reviewer}`.
- `reviewer`는 **결정 파일에 사람이 적은 값만** 쓴다. 도구가 채우지 않고, 비어 있으면 거부한다. 제안한 세션과 결정하는 주체를 분리한다(작성자가 자기 결과를 승인하지 않는 원칙).
- 쓰는 것: `Person`/`Organization`, `MentionIdentification`(accepted/rejected, `assessedAt`, `reviewedBy`, `identificationEvidence`, `identificationMethod`). rejected도 남긴다(같은 후보가 큐에 다시 올라오지 않도록).
- 게이트: 도메인 SHACL(충분성 규칙, Person 공인 근거 게이트, IRI 형식) → 통과해야만 씀. 위반이면 아무것도 쓰지 않고 이유를 보고.
- 멱등: 같은 결정 재적용은 변화 없음. 이미 accepted인 대상에 상충하는 결정이 오면 거부(`revoked`로 바꾸려면 명시 결정).

## 5. 놓인 위치 (가장 큰 설계 결정)

해석 층(Person·Organization·MentionIdentification)을 어디에 둘지가 갈린다. 제약 두 개가 맞물린다.

1. `skb-ontology validate`는 모든 인스턴스를 `skb:declaresTerm`으로 선언한 term으로, object property의 대상도 선언된 term으로 요구한다(L1/L2). 식별은 evidence 층의 mention·account를 가리키므로 ontology 도메인에 두면 **대상이 dangling**이 된다.
2. 도메인 SHACL의 `PersonShape`(공인 근거 게이트)는 **Person과 accepted 식별이 같은 그래프**에 있어야 평가된다.

| 안 | 내용 | 득 | 실 |
|---|---|---|---|
| **A (권장)** | Person·Organization·MentionIdentification 모두 `evidence/identity/`. 관찰 층(`registrations/`)과 같은 층, `identity check`의 SHACL로 검증 | 검증기 변경 0. PersonShape가 그대로 동작. 카탈로그가 같은 층의 그래프를 읽어 상태 계산 | Person이 ontology 도메인의 정식 term이 아님. 다른 도메인이 참조하려면 승격 단계 필요 |
| B | Person·Organization만 ontology 도메인(선언 term), 식별은 evidence 층 | Person을 ontology가 직접 참조 | PersonShape를 식별과 분리해야 해서 shape 분할·두 층 합쳐 검증하는 도구 필요. 도메인 단독 `validate`가 Person 게이트를 못 봄 |
| C | 전부 ontology 도메인, mention·account도 stub으로 선언 | 단일 계약 | 선언된 term 라벨 중복 게이트(D1)가 이름 중복 mention과 충돌. 언급 3천 개를 term으로 선언 |

권장은 **A**다. 이후 필요해지면 "승격" 도구(accepted Person을 선언 term으로 내보내기)를 따로 둔다. 되돌림 비용이 낮다(경로 상수와 shape 위치).

## 6. 카탈로그 연결

- `catalog`가 `evidence/registrations/`와 `evidence/identity/`를 읽어 문서별 `authorMentionCount`, `authorResolvedCount`, `authorshipState`를 계산한다. 해소된 저자는 `dcterms:creator <Person IRI>`로도 싣는다(어휘 주석에 이미 예고).
- `ec:authorRaw`(선언된 이름)는 지우지 않는다. 선언과 해석을 둘 다 남긴다.
- `catalog-validate`: ① 상태 = 재계산값 ② `resolved`/`partial` 문서의 `dcterms:creator`가 존재하는 accepted 식별의 Person을 가리킴 ③ `authorshipReason`은 `unresolved`에만.
- SHACL: `ec:authorMentionCount`·`authorResolvedCount` 정수, resolved이면 두 값이 같고 0보다 큼.

## 7. 프라이버시·안전 규칙

- `Person`은 강하거나 중간 근거의 accepted 식별이 있을 때만(기존 게이트). 근거 없는 개인은 mention·account로만 남는다.
- 큐 파일과 결정 파일에는 PII를 새로 만들지 않는다: 선언된 이름·계정 핸들·공개 소속만(도메인의 `declaredBio` 300자 제한 유지).
- 자동 해소·자동 병합·모델 판정으로 accepted를 만드는 경로는 **없다**. 이 불변식을 테스트로 고정한다(`reviewer` 없는 accepted 거부, 큐에서 accepted가 생성되지 않음).

## 8. 테스트 계획

| 영역 | 확인 |
|---|---|
| propose | 같은 계정을 관찰한 mention들이 한 후보로 묶임, 이름 군집은 병합되지 않고 제안만, 이미 accepted/rejected인 대상은 큐에서 빠짐, 큐 외 파일을 쓰지 않음, 결정적 출력 |
| apply | reviewer 없음 거부, 약한 근거 1개 accepted 거부(충분성), Person 공인 게이트, rejected 기록과 재제안 억제, 멱등, 상충 결정 거부, SHACL 위반 시 무쓰기 |
| catalog | 해소 0/일부/전부 → unresolved/partial/resolved, 개수 일치, 손으로 고친 resolved를 `catalog-validate`가 잡음, 해소된 저자의 `dcterms:creator` |
| 실데이터 | KB 분량으로 propose 시간·큐 크기 확인(후보 수, 계정 기반 vs 이름 군집 비율) |

## 9. 승인이 필요한 결정

1. **위치 A**(해석 층도 `evidence/identity/`)로 가도 되는가.
2. 상태의 재정의(§3)와 **개수 속성 2개 추가**, 그리고 `catalog-validate`의 **재계산 일치 게이트**에 동의하는가.
3. `reviewer`는 결정 파일에 사람이 쓴 값만 인정하고 도구가 채우지 않는다 — 이 엄격한 규칙으로 가도 되는가. (대안: `--reviewer`를 CLI 인자로 받되 환경 변수·세션 정보에서 자동 추론은 금지.)
4. 이름만 있는 군집 후보를 큐에 **올릴지**. 올리면 검토 부담이 크고, 안 올리면 계정 있는 저자만 해소 대상이 된다. (권장: 올리되 영향 문서 수 기준 상위 N개만, 기본 N=50.)
5. 외부 조회(OpenAlex·ORCID 등)로 `identificationEvidence` 후보를 채우는 도구를 **이번 범위에 넣을지**. (권장: 제외. 근거 IRI는 사람이 가져오고, 조회 도구는 별도 승인.)

## 10. 구현 순서 (승인 후)

1. `evidence/identity` 레이아웃 키 + `identity propose` + 테스트
2. `identity apply` + `identity check` + 불변식 테스트
3. 카탈로그 상태·개수 계산, 어휘·SHACL·`catalog-validate` 재계산 게이트
4. KB 실데이터로 propose 규모 확인(쓰기 없음)
5. SKILL.md·core.md·changelog 갱신

## 11. 구현 결과 (2026-10-06)

승인된 결정: 위치 A(`evidence/identity/`), 상태 재정의 + 개수 속성 2개 + 재계산 일치 게이트, `reviewer`는 사람이 쓴 값만, 이름 군집 상위 50개 큐 포함, 외부 조회 제외. 용어는 `IdentityClaim` → `MentionIdentification`(§본문 치환 완료).

**초안과 달라지거나 구체화한 점**
- 그래프(`identifications.ttl`)에는 **현재 accepted 인 식별만** 투영한다. reject·revoke 는 `decisions.jsonl`(append-only 감사 로그)에만 남는다. 이유: 도메인 `PersonShape` 가 accepted 식별이 있는 Person 만 허용하므로, 거절된 후보의 Person 노드를 그래프에 둘 수 없다. 재제안 억제는 로그로 한다.
- 상태 기계: 없음→accept|reject, accept→revoke(reject 로 되돌릴 수 없음), reject→accept 허용, 다른 정체성으로 재accept 는 revoke 먼저.
- `reviewer` 검사는 에이전트·모델 이름 포함 여부(claude, codex, gpt, gemma, gemini, luna, llm, agent, bot, assistant, copilot, sol)를 거르는 **최선의 방어선**이다. 사람임을 증명하지는 못한다. 이 도구가 `decisions.jsonl` 을 쓰지 않는다는 구조가 본 방어다.
- 계정 단위 결정 하나가 그 계정을 관찰한 모든 언급을 해소한다. 이름 군집 결정은 `targets` 배열로 언급마다 식별 하나를 만든다.
- 문서 매칭은 IRI base 가 아니라 `dcterms:source`(URL)로 한다(catalog 와 register 의 base 가 달라도 동작).
- 카탈로그 재계산 게이트: 등록이 있는 문서는 등록·식별에서, 없는 문서는 raw 선언 저자 수(해소 0)에서 계산한다(빌더와 검증기가 같은 규칙).

**실데이터(consumer KB, 문서 692·등록 564)**: propose 0.7초, 큐 107행(계정 57 + 이름 군집 50, 군집 전체 2,457개 중 상위). accepted 0이므로 resolved 문서 0 — 기대치(§2)대로이며 `catalog-validate` 통과.

**테스트**: identity 36개(큐 결정성·상한, 결정 거부 규칙, 상태 기계, SHACL 게이트, 손 편집 탐지, 카탈로그 연동·재계산 게이트).
