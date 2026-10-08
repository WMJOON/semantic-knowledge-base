---
name: skb-semantic-search
description: |
  SKB KB 의 SKOS 개념과 evidence 청크를 의미 검색한다 (EmbeddingGemma 2 768차원 + zvec).
  파생 인덱스를 만들고(index), 메타데이터 필터·문서 단위 묶음으로 검색하고(search),
  원천이 바뀌었는지 신선도를 점검한다(status). 정본(TTL, seeds.jsonl)은 읽기만 하고 수정하지 않는다.
  트리거: "의미 검색", "개념 검색", "evidence 검색", "비슷한 개념 찾아줘", "임베딩 인덱스", "재색인", "인덱스 최신인지".
metadata:
  version: "0.1.0"
---

# skb-semantic-search (v0.1.0)

## What

KB 의 두 정본을 임베딩해 질의로 찾는 **파생 인덱스**와 그 CLI.

| 인덱스 | 원천(정본) | 한 항목 | 임베딩 텍스트 |
|---|---|---|---|
| `concepts` | `ontology/system/semantic/**/*.ttl` 의 `skos:Concept` | 개념 1개 | `prefLabel(en/ko) (altLabel): scopeNote` |
| `evidence` | `evidence/seeds.jsonl` + `evidence/md/*.md` | 청크 1개 | frontmatter 를 뺀 본문 |

인덱스는 `<KB>/embedding/zvec_store_{concepts,evidence}_eg2/` 와 `search_manifest.json` 에 둔다. **언제든 지우고 다시 만들 수 있는 파생물**이라 git 에 올리지 않는다.

## 원칙

1. **문서 소속은 메타데이터다.** 어느 문서의 청크인지는 임베딩 유사도로 추정하지 않고 `uri` 필드로 다룬다. 한 문서로 제한하거나(`--uri`, `--uri-contains`) 문서당 최고 청크만 보려면(`--group-by-doc`) 필터·그룹을 쓴다.
2. **deprecated 개념은 기본 제외.** 켜려면 `--include-deprecated`. `status` 가 빈 개념은 포함된다.
3. **신선도를 먼저 본다.** 검색 결과가 이상하면 `status` 부터 돌린다. 원천 내용 지문, 모델, 차원, `--limit` 부분 적재 여부를 manifest 와 비교한다.
4. **정본을 대신하지 않는다.** 검색 결과의 개념·청크는 후보다. 인용·판단은 TTL 과 `evidence/raw` 원문으로 확인한다.

## Entry Points

| 명령 | 설명 |
|---|---|
| `scripts/skb-semantic-search index concepts --target KB` | TTL 에서 개념을 추출(`rdflib` 필요)해 전체 재색인. 약 1,200개에 6초 |
| `scripts/skb-semantic-search index evidence --target KB [--limit N]` | seeds 의 md 본문 전체 재색인. 4.3만 청크에 약 12분. `--limit` 은 시험용이며 status 가 partial 로 보고한다 |
| `scripts/skb-semantic-search search concepts "질의" --target KB [-k 5] [--status accepted,draft] [--include-deprecated] [--scheme IRI] [--json]` | 개념 검색 |
| `scripts/skb-semantic-search search evidence "질의" --target KB [-k 5] [--uri URL \| --uri-contains STR] [--group-by-doc] [--json]` | 청크 검색 |
| `scripts/skb-semantic-search status --target KB [--json]` | kind 별 `fresh \| stale \| missing`. 하나라도 아니면 종료 코드 1 |
| `scripts/skb-semantic-search extract --target KB` | 개념 JSONL 만 추출(`<KB>/embedding/kb_concepts.jsonl`) |

공통 옵션 `--store-dir DIR` 로 인덱스 위치를 바꾼다(기본 `<KB>/embedding`). `--json` 은 stdout 에 JSON 만 쓰고 zvec 네이티브 로그는 stderr 로 간다.

## 환경

- 임베딩·검색: `SKB_SEARCH_PYTHON` (기본 `python3`; `mlx-vlm`, `transformers`, `zvec` 필요, Apple Silicon 의 MLX 기준). 모델은 HF 캐시의 `mlx-community/embeddinggemma-2-bf16`.
- 개념 추출: `SKB_RDF_PYTHON` (`rdflib` 필요). 지정이 없으면 현재 python 이 `rdflib` 를 import 할 수 있어야 한다.
- 모델·차원·접두어(`title: none | text: `, `task: search result | query: `)는 `scripts/ss_common.py` 의 상수가 단일 출처다. 바꾸면 manifest 와 달라져 status 가 stale 로 보고하고 전체 재색인이 필요하다.

## 프로바이더

Claude Code, Codex(`~/.agents/skills`), Antigravity CLI(`agy`)에서 같은 `SKILL.md` 로 동작한다. `agy` 는 `~/.gemini/config/skills/` 와 작업 폴더의 `.agents/skills/` 만 전역·워크스페이스 스킬로 읽는다(`~/.gemini/antigravity/skills` 는 읽지 않는다, 2026-10-08 실측). 등록은 `00_agents_global_links/sync-agents-global.sh add skb-semantic-search <경로>` 로 하고, 그 스크립트의 매핑에 `~/.gemini/config/skills` 가 포함돼 있다. 모든 명령은 읽기 전용 검색 외에는 `<KB>/embedding/` 아래에만 쓴다.

## 읽는 법

- `sim` 은 `1 - 코사인 거리`다. 질의 접두어와 문서 접두어가 달라 같은 문서의 sim 이 1.0 이 되지는 않는다.
- `--group-by-doc` 은 후보를 `max(k*8, 50)`(상한 300)개 가져와 문서별로 묶는다. 같은 문서의 청크가 많이 겹치면 반환 문서 수가 k 보다 적을 수 있다.
- 필터는 zvec 필터 식(`=`, `!=`, `like`, `and`, `or`)으로 변환되고 JSON 출력의 `filter` 에 그대로 보인다.

## 한계 (정직하게)

- **중복 감지 임계값은 이 스킬이 제공하지 않는다.** 정답 쌍이 없어 EmbeddingGemma 2 의 유사도 임계값을 보정하지 못했다.
- 검색 품질은 공개 벤치마크로 평가하지 않았다. 개념 검색(질의=prefLabel, 정답=그 개념)은 작성자의 비공개 KB 에서 재현 가능한 대리 지표로만 확인했고, evidence 검색의 정확도는 평가 전이다.
- 증분 갱신이 없다. 원천이 바뀌면 해당 kind 를 전체 재색인한다.
- prefLabel 이 없는 개념과 md 본문이 없는 seed 는 색인에서 빠지고 manifest 의 `skipped` 에 개수가 남는다.
- 어휘(키워드) 검색과 하이브리드 순위는 없다.

## Non-Goals

- 개념·관계 생성 → `skb-ontology`
- evidence 수집·검증 → `skb-evidence`
- 정합 점검 → `skb-ontology validate` (재색인 필요 여부는 이 스킬의 `status` 로 확인)
- 그래프 추론 → `skb-graph-reasoning`

## 테스트

`python -m pytest -q tests` (순수 함수만; mlx·zvec 불필요). 인덱스 생성·검색 동작은 실제 KB 에서 `--store-dir /tmp/...` 로 시험한다.

자세한 필드·manifest 형식은 [references/index-spec.md](references/index-spec.md).
