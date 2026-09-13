---
name: skb-evidence
description: |
  SKB v1.1.2 Fat Skill — 외부 URL/로컬 MD를 수집·청킹·dedup하여
  evidence/seeds.jsonl 및 evidence/md/ 노트를 생성한다.
  entity/relation 생성은 하지 않는다. seed는 skb-ontology의 입력.
  v0.12.2: --capture 로 URL 원문 스냅샷(PDF/PNG/HTML) 박제 + seed.snapshot 기록 (opt-in).
  v1.1.0: raw-ingest 경로 추가 — ingest = [render(playwright-cli, opt)] → convert(docling)
  → collect. JS-rendered 페이지와 PDF/Office 문서를 evidence/raw/ MD 원문으로 적재 (opt-in).
  v1.1.1: collect 가 PDF/오피스 바이너리 응답을 감지하면 UTF-8 강제 디코딩(깨진 seed 조용히
  생성)하지 않고 status="error"+ingest 안내로 fail-loud (consumer KB TS-0007 기반).
  v1.1.2: collect 가 convert.py 산출 local md(중간 파일)를 --source로 받을 때, frontmatter
  의 source: 필드로 seed.uri를 원본 URL로 복원 (원격 fetch 콘텐츠는 신뢰하지 않고 local
  file 한정). ingest 경로 전체(hermes-agent 포함 과거 산출물)에 영향, consumer KB TS-0010 기반.
metadata:
  version: "1.1.2"
---

# skb-evidence (v1.1.2)

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
| CLI — collect | `scripts/skb-evidence collect --target REPO --source URI [...] [--apply] [--capture]` |
| CLI — capture | `scripts/skb-evidence capture --url URL --target REPO` (opt-in; requires playwright) |
| CLI — convert | `scripts/skb-evidence convert --source URI --target REPO` (opt-in; requires docling) |
| CLI — ingest | `scripts/skb-evidence ingest --target REPO --source URI [...] [--render] [--apply]` (opt-in; requires docling, `--render` 시 playwright-cli) |
| CLI — verify | `scripts/skb-evidence verify --target REPO` |
| CLI — list | `scripts/skb-evidence list --target REPO` |
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
  도구 스택 결정 근거: consumer KB work-memory AD-0021/UD-0031 (firecrawl 불채택)

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
