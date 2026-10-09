# Provenance 설계 입장 — claim, 출처, 그리고 AI에게 보내지 않기

SKB가 출처·저자 모델(`source-agents`)과 `skb-evidence` 카탈로그를 이렇게 만든 이유를 정리한다. 어휘 정본은 `skills/skb-ontology/references/domains/source-agents/`다.

## 1. 모든 문서는 사실이 아니라 작성자의 주장(claim)이다

- 물리 세계의 정보를 의미(Semantic)로 온전히 담는 기술은 없고, 우리는 근사할 뿐이다. 이름이 *Semantic* Knowledge Base인 이유는 Semantic Web 언어를 써서만이 아니라, 이 한계를 전제로 설계했기 때문이다.
- 문서가 가공(`prov:Activity`)을 거칠수록 사실에서 멀어진다. 그래서 SKB는 **문서가 선언한 것(관찰)과 우리가 해석한 것을 분리**하고, 신뢰도는 저장하지 않고 조회로 계산한다.
- 에이전트가 쓴 글은 대부분 출처를 추적하는 중간 관문이지 정보의 원천이 아니다. 단, 공신력 있는 발행 주체의 책임 아래 만들어졌다면 그 공신력을 위임받은 것으로 달리 취급할 수 있다.

## 2. 기록하는 메타데이터

| 글의 표현 | SKB 정본 | 비고 |
|---|---|---|
| author | `ec:authorRaw` → 해소되면 `dcterms:creator` | 관찰은 `sa:AgentMention`, 해석은 `sa:Person` + `sa:MentionIdentification` |
| publishedOrganization | `ec:declaredPublisher`, `ec:publisherType` | 호스트에서 도출한 `ec:Publisher`와 구분한다 |
| originSite | `ec:Source`의 `uri`, `ec:issuer` | 별도 `originSite` 속성은 없다 |
| retrieved_at | `prov:generatedAtTime`, `ec:collectedAtBasis` | 원문 frontmatter의 `collected_at` |
| published_at | `dcterms:issued`, `ec:publishedAtSource` | 제공자가 선언한 값만 쓰고 추정하지 않는다 |
| updated_at | — | 카탈로그 어휘에 아직 없다 |

글에서 쓰는 이름은 개념 설명용이며, 코드와 TTL에서는 위 정본 이름을 쓴다.

## 3. 현재 구현과 아직 없는 것

| 항목 | 상태 |
|---|---|
| 관찰과 해석의 분리, 신뢰도 = 공신력 × 성실도(조회로 계산) | 구현됨 (`effective_trust.rq`) |
| accepted 식별은 사람 검토 + 강한 근거 1개 또는 서로 다른 방법 2개 | 구현됨 (SHACL 게이트) |
| 저자 일부만 해소된 문서 허용 (`partial`) | 구현됨 |
| **SoftwareAgent 작성물 필터와 "공신력 있는 발행 주체 책임이면 통과" 예외** | **미구현.** `sa:declaredType`은 `Person \| Organization \| unknown`뿐이고 `SoftwareAgent`·`MediaCompany` 클래스가 없다 |
| **정규화된 식별자의 Hash Lookup** | **미구현.** 식별은 근거 기반 승격이며 결정적 키 조회 경로가 없다 |
| **"누가 말했다"는 인용을 원본 채널에서 찾아 원문 확보** | **미구현** |
| `originSite`, `updated_at` | 미구현 |

미구현 항목은 TBox·SHACL 정본을 바꾸는 일이라 제안과 사용자 승인을 거친 뒤에 추가한다.

## 4. 정책은 SHACL 한 줄 차이로 달라진다

필터 정책은 개념상 다음 한 구조에 달려 있다.

```sparql
?author a prov:SoftwareAgent .
FILTER NOT EXISTS {
  $this skb:publishedOrganization ?org .
  ?org a skb:MediaCompany .
}
```

`FILTER NOT EXISTS` 하나가 빠지면 "에이전트 글은 모두 거른다"가 되어 정책이 완전히 달라진다. 정책을 추가할 때는 예외가 있는 경우와 없는 경우를 **양쪽 모두** 테스트로 고정한다. 위 코드는 설계 예시이며 현재 정본에는 없다(§3).

## 5. 왜 이렇게 하는가: AI에게 보내지 않는 비용 최적화

판정은 결정적 조회가 가능하면 모델에 맡기지 않는다.

- 인용문이 원래 명제를 얼마나 왜곡했는지 LLM으로 판정하기보다, 발언자의 원본 채널을 찾아 해석이 빠진 원문을 가져오는 편이 싸다.
- AI 생성물 비중이 높은 계정은 처리 전에 건너뛴다(bypass).
- 개인 식별 정보를 정규화해 키로 만들면 "같은 사람인가?"를 매번 LLM에게 묻지 않고 조회로 넘긴다. 단 `Person`은 공인 근거가 있을 때만 만든다(프라이버시 게이트).

그래서 중요한 질문은 "무엇을 AI에게 맡길 것인가"만이 아니라 **"무엇을 AI에게 보내지 않을 것인가"**다. 캐싱, Hash Lookup, Provenance 기반 필터링이 그 수단이고, Provenance 관리가 곧 AI 비용을 줄이는 방법이다.
