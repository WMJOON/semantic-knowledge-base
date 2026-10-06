# 제안: 출처·저자 모델(source-agents)을 SKB로 이관

status: **승인(2026-10-06) · 구현 완료(1~3단계)** — 4~5단계는 미착수. 구현 중 달라진 점은 §8
작성: 2026-10-06 · 대상: `skills/skb-ontology`, `skills/skb-evidence` · 원본: consumer KB `ontology/system/semantic/meta/source-agents/`, `harness/source-registration/`

## 1. 무엇을 옮기려는가

consumer KB가 안정시킨 모델은 한 문장으로 "**문서가 선언한 것(관찰)과 우리가 해석한 것을 분리하고, 신뢰도는 저장하지 않고 조회로 계산한다**"이다.

| 층 | 클래스 | 하는 일 |
|---|---|---|
| 관찰 | `AgentMention`, `Account` | 문서가 선언한 저자·발행자 이름, 플랫폼 계정을 있는 그대로 기록. 해소하지 않음 |
| 해석 | `Person`, `Organization`, `MentionIdentification`, `Membership` | 정체성 주장(방법·근거·상태), 소속(유효시간과 관찰시간 분리) |
| 평가 | `TrustFactorAssessment` | 공신력(발행자)·성실도(문서) 평가를 근거와 함께 누적. 덮어쓰지 않고 `supersedes` |
| 파생 | `effective_trust.rq`, `current_membership.rq` | 신뢰도=공신력×성실도(3×3 표), 현재 소속은 조회로 계산 |

핵심 SHACL 게이트: accepted 식별은 사람 검토(`reviewedBy`)와 강한 근거 1개 또는 서로 다른 방법 2개가 필요, `Person`은 공인 근거가 있을 때만 생성(프라이버시), 파생값(`memberOf`, 신뢰도) 저장 금지, 계정 키는 핸들이 아니라 (플랫폼, 불변 ID).

## 2. SKB에 이미 있는 것과의 접점

- `skb-evidence` v1.2.0 카탈로그: `ec:authorRaw`, `ec:authorshipState`(resolved|partial|unresolved), `ec:declaredPublisher`, `ec:accountJson`. **이 값들이 `sa:AgentMention`/`sa:Account`로 승격되는 자리**다. 카탈로그 어휘 주석이 이미 "해소되면 `dcterms:creator`로 source-agent IRI를 가리킨다"고 선언해 두었다.
- `skb-ontology` 레지스트리 규칙: 모든 term에 `rdfs:label`·`dct:identifier`·`prov:hadPrimarySource`·`skb:status`. KB의 TBox는 이미 이 형식을 따른다.

## 3. 일반화가 필요한 부분 (KB 전용 → SKB 범용)

| 항목 | KB 현재 | SKB 제안 |
|---|---|---|
| 네임스페이스 | `https://wmjoon.kb/ontology/meta/source-agents#` | `https://skb.dev/ontology/source-agents#` (카탈로그 `ec:`와 같은 `skb.dev` 계열) |
| 인스턴스 IRI | `https://wmjoon.kb/person/…`, `/account/…` 고정 | `--base` 인자로 주입 (카탈로그와 같은 방식) |
| `prov:hadPrimarySource` | 특정 연구 보고서 1건을 전 term의 근거로 사용 | SKB 설계 문서(이 제안서의 승인 기록)를 근거 IRI로 두고 `--evidence`로 교체 가능하게 |
| 생성 방식 | `gen_source_agents_schema.py`로 TTL 생성 | **생성기 없이 TTL 정본을 직접 둔다**(SKB의 TTL-only 원칙. 생성기는 migration 이력일 뿐) |
| 문서 유형 어휘 | `source-type-paper`만 | `paper`·`unknown`(카탈로그 `ec:documentType`과 일치)로 시작, 추가는 사용자 결정 |
| 평가 주제 | `aboutTopic`이 KB의 SKOS 개념을 가리킴 | 선택 속성 유지(없어도 동작) |

## 4. 옮길 것 / 미룰 것

**이번에 옮김 (안정)**
1. `skb-ontology` 도메인 `source-agents`: schema·vocabulary·shapes TTL (TBox 정본 후보, status `draft`)
2. SPARQL 질의 2개(`effective_trust.rq`, `current_membership.rq`)와 SHACL 테스트
3. `skb-evidence`에 **`register` 게이트**: 카탈로그의 `authorRaw`/`accounts`를 `AgentMention`/`Account`로 **결정적으로** 변환하는 단계(모델이 쓴 triple 없음, 신원 승격 없음)

**미룸**
- Gemma 이상탐지·LangGraph 컴파일(`register.py`의 후반): oMLX 서버와 모델 상주가 전제라 SKB 코어 의존성으로 부적합. 결정적 lexical 검사(비정상 공백·mojibake·NFC·이름 토큰 자리바꿈)만 옮기고, 모델 단계는 **선택 플러그인**으로 분리 제안.
- cascade `author-check`(정확도 0.84~0.90, 정답이 teacher 라벨뿐): 실험 단계라 제외.
- Trend Radar 전용 수집·`trend-source-registration` workflow: consumer 전용.

## 5. `register` 게이트의 계약 (제안)

```
입력  : evidence/catalog/catalog.ttl 의 ec:Source (+ 대응 raw frontmatter)
출력  : ontology/system/semantic/source-agents/registrations/<doc-key>.ttl
만든다: prov:Entity(문서), sa:AgentMention(저자·발행 선언), sa:Account(accounts 배열)
만들지 않는다: Person, MentionIdentification(accepted), TrustFactorAssessment, 모델이 쓴 triple
저자가 없으면: 저자를 만들지 않고 ec:authorshipReason 을 보존한다
기본값: dry-run, --apply 로 쓴다. 같은 문서·스냅샷은 기존 등록 보존, 내용이 달라진 같은 버전은 중단
```
`sa:AgentMention`에는 `sa:inDocument`, `sa:mentionRole`, `sa:declaredName`, `sa:declaredType`, `prov:generatedAtTime`, `prov:wasDerivedFrom`(스냅샷 IRI)이 필수다.

## 6. 승인이 필요한 결정

1. **네임스페이스 `https://skb.dev/ontology/source-agents#`** 로 가도 되는가 (KB의 `wmjoon.kb` 네임스페이스와 갈라지므로, KB 쪽은 별도 마이그레이션 전까지 그대로 둠).
2. `Person` 생성 게이트(공인 근거 필요)를 **SKB 기본 SHACL에 그대로 포함**할지, 프라이버시 정책이 다른 사용자를 위해 선택 shape로 분리할지.
3. 모델 이상탐지를 코어에서 빼고 플러그인으로 두는 것에 동의하는가.
4. 문서 유형 어휘를 `paper|unknown`으로 시작해도 되는가.

## 7. 구현 순서 (승인 후)

1. 도메인 TTL 3종 + SPARQL 2종 이관, `skb-ontology validate` 통과 확인
2. SHACL 긍정·부정 테스트 이관(`test_source_agents_shapes.py`, `test_trust_factor_assessment.py`)
3. `skb-evidence register` + lexical 검사 + 테스트
4. 카탈로그 `authorshipState`가 resolved가 되는 경로 연결, `catalog-validate`에 상호 참조 검사 추가
5. `docs/changelog.md`, SKILL.md 갱신

## 8. 구현 결과와 초안에서 달라진 점 (2026-10-06)

사용자가 초안을 승인했다("좋아"). 결정 2번(Person 생성 게이트)은 선택지만 제시했으므로 **기본 SHACL에 그대로 포함**하는 쪽으로 진행했다(KB에서 검증된 동작, 프라이버시 쪽 기본값). 되돌리려면 `PersonShape`를 선택 shape 파일로 분리하면 된다.

| 초안 | 실제 | 이유 |
|---|---|---|
| 출력 `ontology/system/semantic/source-agents/registrations/` | **`evidence/registrations/<document-key>.ttl`** | `skb-ontology validate`는 모든 인스턴스를 `skb:declaresTerm` 선언 term으로 요구한다(L1/L2). 문서마다 쌓이는 AgentMention·Account(KB 실데이터 기준 문서 566개, 언급 3,298개)를 term으로 선언하면 라벨 중복 게이트(D1)와 충돌한다. 카탈로그(`evidence/catalog`)와 같은 관찰 층으로 두고 `register --check`의 SHACL로 검증한다. |
| 인스턴스 IRI 패턴을 `skb.dev` 아래 고정 | `https?://<호스트>/(접두/)?<종류>/<키>` 패턴 | `--base`를 사용자가 정하므로 호스트·접두는 검사하지 않고 종류 경로(`/person/` 등)와 슬러그·해시 형식만 검사한다. 이 때문에 "Person 다른 네임스페이스" 테스트를 "종류 경로 없음"으로 바꿨다. |
| `Account.hadPrimarySource` = 플랫폼 API URL | 원문 스냅샷 IRI | raw frontmatter에 API URL이 기록되지 않는다. 선언 출처는 `accounts_source`에만 있다. |
| `prov:generatedAtTime` = 등록 시각 | raw의 `collected_at` | 결정적 출력(같은 입력 → 같은 파일)을 위해. |

실데이터 확인(KB seed 42,377행, 카탈로그 문서 692개): `register` dry-run이 raw가 연결된 566개 문서 전부 통과, 언급 3,298개·계정 76개, lexical 지적 0건.

**미착수**: 4단계(카탈로그 `authorshipState=resolved` 경로와 `catalog-validate` 상호 참조 검사), 5단계 일부. resolved는 MentionIdentification accepted(사람 검토)가 있어야 하므로 별도 HITL 설계가 필요하다.

### 용어 변경 (2026-10-06)

`IdentityClaim` 은 이름이 "문서가 한 주장"으로 읽히고 KB 의 `claim`(명제) 어휘와 충돌해 **`MentionIdentification`** 으로 바꿨다. 이 레코드는 문서가 아니라 우리가 검토해서 내리는 식별 결정이다. 속성도 함께 바꿨다: `claimsIdentity`→`identifiesAs`, `claimStatus`→`identificationStatus`, `claimEvidence`→`identificationEvidence`, `identityMethod`→`identificationMethod`. 인스턴스 IRI 종류 경로는 `/claim/`→`/identification/`. 대상 속성(`aboutMention`, `aboutAccount`)과 개념 스킴(`identity-methods`)은 유지. 본문 §1~§7 의 옛 용어는 이 표기로 읽는다(아래 치환 후 문서 전체 갱신됨).
