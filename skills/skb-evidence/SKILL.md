---
name: skb-evidence
description: |
  SKB v1.2.0 Fat Skill — 외부 URL/로컬 MD를 수집·청킹·dedup하여
  evidence/seeds.jsonl 및 evidence/md/ 노트를 생성한다.
  entity/relation 생성은 하지 않는다. seed는 skb-ontology의 입력.
  v0.12.2: --capture 로 URL 원문 스냅샷(PDF/PNG/HTML) 박제 + seed.snapshot 기록 (opt-in).
  v1.1.0: raw-ingest 경로 추가 — ingest = [render(playwright-cli, opt)] → convert(docling)
  → collect. JS-rendered 페이지와 PDF/Office 문서를 evidence/raw/ MD 원문으로 적재 (opt-in).
  v1.1.1: collect 가 PDF/오피스 바이너리 응답을 감지하면 UTF-8 강제 디코딩(깨진 seed 조용히
  생성)하지 않고 status="error"+ingest 안내로 fail-loud (소비자 KB 에서 재현된 사례 기반).
  v1.1.2: collect 가 convert.py 산출 local md(중간 파일)를 --source로 받을 때, frontmatter
  의 source: 필드로 seed.uri를 원본 URL로 복원 (원격 fetch 콘텐츠는 신뢰하지 않고 local
  file 한정). ingest 경로 전체(과거 산출물 포함)에 영향, 소비자 KB 에서 재현된 사례 기반.
  v1.1.3: convert 가 docling 을 --image-export-mode placeholder 로 호출하고 본문 data URI(base64)
  이미지를 제거한다. 기본 embedded 모드는 PDF 그림을 본문에 넣어 청킹이 이미지 조각 seed 를 대량
  생성했다(mixed-precision 리서치: seed 80%). GitHub blob/raw 텍스트(.md/.py/.cpp 등)는 docling 이
  산출물을 못 만들 때 raw 내용을 직접 받아 적재(converter: raw-fetch). tests/test_convert.py 추가.
  v1.1.4: 모든 원문(evidence/raw)은 수집일을 반드시 표기한다. convert 가 frontmatter 에 collected_at(수집 시작
  시각, UTC), collected_at_basis, published_at(제공자가 등록한 발행일, 없으면 'unavailable'), published_at_source
  (예: jsonld:datePublished, arxiv:citation_date, github-api:created_at, none:<사유>)를 기록한다. 발행일은
  제공자가 선언한 값만 쓰고 본문·URL·파일 시각으로 추정하지 않는다(scripts/provenance_dates.py). verify 는 원문의
  collected_at/published_at 누락을 실패로 보고하고, 수동 작성 seed 의 content_hash 부재로 죽던 문제를 고쳤다.
  v1.1.5: 원문 frontmatter 에 발행 주체 publisher(+publisher_source, 선언값과 domain-derived 구분), 발행 주체 유형
  publisher_type(Organization|Person|unknown, 제공자 선언값만: GitHub·HF API, JSON-LD @type), 저자 authors(JSON 배열,
  문서가 선언한 저자와 선언된 소속만; 본문 by-line 은 긁지 않는다)와 authors_source 를 기록한다. verify 가 누락을 실패로 보고한다.
  저자·발행 주체·계정 유형은 섞지 않고 각각 기록한다(신뢰도 모델링의 전제).
  v1.2.0: 검증체계 강화(consumer KB 이관). verify 가 seed id 중복·청크 본문-content_hash 불일치·snapshot 파일 부재·uri 부재를
  잡는다(--shallow 로 본문 대조 생략). verify-quotes 는 claims.json 의 fact quote 가 원문에 글자 그대로 한 번 있는지, inference basis 가
  fact 인지를 결정적으로 검사한다(의미 판정은 작성자와 다른 검증자의 몫). catalog 는 seeds.jsonl 을 발행자·문서·청크 프로파일 TTL(ec: 어휘,
  SHACL)과 chunks.jsonl 로 정규화하고 raw frontmatter 의 날짜·저자·발행 주체 선언값을 문서에 싣는다. catalog-validate 는 SHACL 과
  TTL↔JSONL 정합, rawPath 존재를 게이트한다. register 는 카탈로그 문서의 저자·발행 주체·계정 선언을
  source-agents 도메인(skb-ontology/references/domains/source-agents)의 AgentMention·Account 로 결정적으로 등록한다. Person·MentionIdentification·
  신뢰 평가·모델 triple 은 만들지 않고, lexical 검사와 SHACL 을 통과해야 쓴다. identity 는 저자 신원 해소 HITL 이다: propose 가 결정적
  후보 큐(계정 단위 + 이름 군집 상위 N)를 만들고, 사람이 decisions.jsonl 에 결정(reviewer 필수, 에이전트 이름 거부)을 쓰면 apply 가
  현재 accepted 인 MentionIdentification 만 identifications.ttl 로 투영한다(도구가 accepted 를 만드는 경로 없음). 카탈로그의
  authorshipState 는 저자 언급 수·accepted 해소 수에서 계산되고(authorMentionCount/authorResolvedCount), catalog-validate 가 재계산 일치를 게이트한다.
metadata:
  version: "1.2.6"
---

# skb-evidence (v1.2.5)

## What

외부 원본(URL, 로컬 MD, JS-rendered 페이지, PDF/Office 문서)을 받아 검증 가능한
evidence seed를 생산하는 Fat Skill.

책임:
1. **수집**: URL / 로컬 MD 파일을 fetch
2. **변환** (v1.1.0, opt-in): JS-rendered 페이지는 playwright-cli 렌더링,
   정적 URL·HTML·PDF·Office 문서는 docling으로 `evidence/raw/` MD 원문 변환
3. **청킹**: 큰 문서를 검색·인용 가능한 단위로 분할
4. **dedup**: content-hash(sha256) 기반 중복 제거
5. **seed 등록**: `evidence/seeds.jsonl`에 append, `evidence/md/`에 노트 저장

자세한 동작은 [core.md](core.md) 참조.

## Entry Points

| 진입점 | 명령 |
|--------|------|
| CLI — collect | `scripts/skb-evidence collect --target REPO --source URI [...] [--apply] [--capture] [--searched-at ISO_Z --search-query Q] [--request-params JSON]` — seed.retrieval 에 최종 URL·상태·형식·응답 해시를 기록, 검색으로 찾은 문서만 검색 시각 |
| CLI — capture | `scripts/skb-evidence capture --url URL --target REPO` (opt-in; requires playwright) |
| CLI — convert | `scripts/skb-evidence convert --source URI --target REPO` (opt-in; requires docling) |
| CLI — ingest | `scripts/skb-evidence ingest --target REPO --source URI [...] [--render] [--apply]` (opt-in; requires docling, `--render` 시 playwright-cli) |
| CLI — verify | `scripts/skb-evidence verify --target REPO [--shallow] [--no-catalog] [--orphans [--strict]]` — 카탈로그가 있으면 SHACL·정합도 함께 점검(seeds 와 어긋나면 경고) |
| CLI — list | `scripts/skb-evidence list --target REPO [--catalog] [--format table\|json\|ids]` — `--catalog` 는 문서 단위(발행자·URL·청크 수·시점) |
| CLI — verify-quotes | `scripts/skb-evidence verify-quotes --claims claims.json [--target REPO] [--report report.md]` |
| CLI — catalog | `scripts/skb-evidence catalog --target REPO [--base IRI] [--publishers FILE] [--enricher legal-kr] [--apply]` (rdflib 필요). `--publishers` 는 저장소가 소유하는 발행자 규칙(배포처 `publisher`와 원 발행처 `issuer` 분리), `--enricher` 는 도메인 확장 어휘(`ecl:`)와 청크 `locators` 를 켠다 |
| CLI — register | `scripts/skb-evidence register --target REPO [--base IRI] [--apply \| --check]` (rdflib, pyshacl 필요) |
| CLI — identity | `scripts/skb-evidence identity propose\|apply\|check --target REPO [--apply]` (rdflib, pyshacl 필요) |
| CLI — catalog-validate | `scripts/skb-evidence catalog-validate --target REPO` (rdflib, pyshacl 필요) |
| CLI — graphify ETL | `scripts/graphify_to_skb.py graph.json [--output-dir OUT] [--sigma 2.0]` |
| Harness | `harness/run.sh --skill skb-evidence --tier L0 --mode validate-only --target REPO` |
| Workflow | `agent-context/workflow/evidence/graphify-etl.abox.ttl` |

## Triggers

- "evidence 수집", "seed 수집", "URL 크롤링"
- "Ralph", "ETL", "논문 수집"
- "skb-evidence collect"

## Dependencies

- Python 3.10+
- 코어(collect/verify/list): 외부 패키지 없음 (stdlib만: urllib.request, html.parser, hashlib)
- Bash (CLI wrapper, harness)
- opt-in (raw-ingest 경로): `docling` CLI (`uv tool install docling`),
  `--render` 시 `playwright-cli` (`npm install -g @playwright/cli`).
  부재 시 graceful degrade — 코어 경로는 영향 없음.
  도구 스택 결정 근거: firecrawl 불채택, docling 채택 (소비자 KB 의 결정 기록)

## Source Types

| 소스 타입 | 스크립트 | 출력 |
|---------|---------|------|
| URL / 로컬 MD | `scripts/skb-evidence collect` | `evidence/seeds.jsonl`, `evidence/md/` |
| JS-rendered 페이지 | `scripts/skb-evidence ingest --render` | `evidence/captures/<sha12>.html`, `evidence/raw/*.md`, seeds |
| 정적 URL·HTML·PDF·DOCX·XLSX·PPTX | `scripts/skb-evidence ingest` (또는 `convert`) | `evidence/raw/*.md`, seeds |
| Graphify `graph.json` | `scripts/graphify_to_skb.py` | `evidence/graphify/entity_candidates.jsonl`, `evidence/graphify/relation_candidates.jsonl` |

Graphify ETL은 `file_type==concept` 노드만 통과시키는 Semantic Lifting Layer(Option A).
`code` 타입 노드는 버리고, god node(degree 2σ 초과)는 `hub_candidate` 태그 부여.

`collect`는 PDF/오피스 바이너리 응답을 감지하면(content-type·magic bytes 확인) UTF-8
강제 디코딩으로 깨진 seed를 만드는 대신 `status="error"` + `ingest` 사용 안내로 fail-loud
한다(v1.1.1). PDF·Office 문서는 항상 `ingest`/`convert`(docling)를 쓴다.

## Non-Goals

- entity/relation/instance 생성 → `skb-ontology`
- LLM 기반 claim 추출 → v0.11
- 사이트 전체 crawl·map (링크 자동 발견·대량 수집) — 필요 시 별도 도구(firecrawl 등) 재검토
