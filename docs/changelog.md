# Changelog

## v1.7.0 (2026-10-09) — publisher candidates in `identity propose`, publisher kinds in the `source-agents` pack

### Added

- **`skb-evidence identity propose`** now also queues the publisher a document declared (`target_kind: publisher_cluster`), grouped by
  normalized name. Publishers inferred from the host (`publisher_source: domain-derived`) are never proposed, publisher rows are not
  capped by `--max-clusters`, and nothing is promoted without a human entry in `decisions.jsonl`. Before this, only accounts and author
  name clusters were queued, so a declared publisher had no route to `sa:Organization`. Tests: `test_identity_publisher.py`.
- **`source-agents` domain pack:** a `publisher-kinds` concept scheme (repository, preprint repository, institutional repository, journal
  publisher, government agency, web publisher) and the `sa:publisherKind` property for `sa:Organization`. A kind classifies; it does not set trust.
- **`skb-evidence` SKILL.md:** the fixed procedure after collecting sources (collect → catalog with `--publishers` → register scoped with
  `--source` → identity candidates → human decision → validate), including the rule that a name declared by the document is `curation: known`
  while a host-derived name stays `auto`.

### Changed

- Removed the last internal record identifiers from comments and docs (`skb-repository-setup` layering notes, the agent-consumption contract).

## Unreleased — provenance design stance (docs only)

- Added `docs/guides/provenance-stance.md` (Korean): the claim-is-not-fact premise, a table mapping metadata terms to the canonical names,
  what is implemented vs. proposed (SoftwareAgent filter, hash lookup and original-channel retrieval are not implemented), and the
  "what not to send to an AI" cost view. A short section in the README links to it. No code, TBox or SHACL change.

## v1.6.1 (2026-10-09) — b1 scaffold: declare the layer modules the artifact registry points to

### Fixed

- The b1 `agent-context/index/index.yaml` now declares `skb-ontology-layer`, `skb-evidence-layer`, `skb-harness-layer` and `skb-report-layer`
  (with their paths). The artifact registry's `wf:inModule` and directory templates referred to modules the index did not list, so the
  MSO artifact-layer check reported 5 cross-layer violations (it is not available in CI, so v1.6.0 did not catch it).
  `test_scaffold_end_to_end.py` now checks that every `wf:inModule` is declared and that each directory template lies under its module path.

## v1.6.0 (2026-10-09) — `skb init` aligned with the published tools

### Added

- **`skb init --layout b1|legacy`** (default `b1`). `b1` scaffolds `ontology/semantic/<domain>/`, `evidence/{artifact/raw,chunk,catalog}` and
  declares those paths in a `layout:` section of `canonical_root_hub.yaml`. Turtle stays the canonical store; no JSONL registries are created.
  `legacy` reproduces the previous tree byte for byte.
- **TTL-only workflow templates** (`wf:`/`skbx:`): evidence-collection, ontology-construction, validation, search-reason, plus an
  `agent-context/index/artifacts.abox.ttl` artifact registry. search-reason now runs real steps (`skb-semantic-search` status,
  `skb-graph-reasoning` check) instead of the retired explorer tool.
- **`.gitignore` template** excluding raw evidence, derived embeddings and inferred graphs, and run records. An existing `.gitignore` is never overwritten.
- `harness/run.sh` for `skb-graph-reasoning` (check) and `skb-semantic-search` (status; a stale or missing index is reported, not failed).
- Oracle `repository_integrity` (`skb-repository-setup`).
- `validate_workflows.py` lints references: every `skbx:tool` / `tool:` must be a skill with `harness/run.sh`, every oracle an existing file.
  It accepts TTL-only workflow sets.
- `tests/test_scaffold_end_to_end.py`: init output is read and run by the published CLIs, the harness gives a real oracle score for each workflow,
  and a KB without a `layout:` section keeps the old paths.

### Changed

- Every skill resolves the semantic directory and the seeds file through `layout:` (`skb-ontology`, `skb-graph-reasoning`, `skb-semantic-search`,
  `skb-evidence` oracle and L0 validator). A KB without `layout:` behaves as before.
- `layout.py` no longer ignores a declared `layout:` when PyYAML is missing (it reads the flat block and says so on stderr).
- `validate_repository_setup.py` derives the required directories from the scaffold manifest instead of a second hand-kept list.
- Legacy YAML workflow templates and the repository's own workflows now name existing tools and oracles (`ontology_readiness`,
  `skb-semantic-search`, `skb-graph-reasoning`); the retired `msm-graph-reasoning` and three non-existent oracle names are gone.

## v1.5.0 (2026-10-08) — skb-evidence 1.2.5: source catalog, quote verification, source-agent registration

### Added

- **`catalog` / `catalog-validate`**: normalizes `seeds.jsonl` into publisher / document / chunk profiles (`ec:` vocabulary, SHACL)
  plus `chunks.jsonl`. Dates, authors and publishers declared in the raw frontmatter are carried onto the document.
  Retrieval is modelled as `ec:Retrieval` (searched / retrieved / collected times, request URL, method, params, status,
  media type, response hash); chunks keep `char_start`/`char_end`. `--publishers FILE` lets the repository own publisher rules
  (distributing site vs. issuing body), `--enricher NAME` adds a domain extension outside the core vocabulary (`legal-kr`).
- **`verify-quotes`**: a `claims.json` fact quote must appear verbatim exactly once in the raw source, and an inference must rest on facts.
  It does not judge meaning.
- **`register`**: registers the authors, publishers and accounts a catalog document declares as source-agent `AgentMention`/`Account`
  observations (needs the `source-agents` pack from v1.4.0). It creates no Person, identification, trust assessment or model triple.
- **`identity propose|apply|check`**: author identity resolution as a human-in-the-loop step. `propose` builds a candidate queue
  (per account, and name clusters) and never merges automatically; only decisions a reviewer wrote to `evidence/identity/decisions.jsonl`
  are applied.
- **Retrieval record**: `collect`, `ingest` and `convert` accept `--searched-at` (with `--search-query`) and `--request-params`;
  `collect` writes a per-document `retrieval` object (final URL, method, status, media type, response hash).
- `verify --orphans [--strict]` reports `evidence/md` notes that no seed references.

### Changed

- `verify` also checks duplicate seed ids, chunk body vs. `content_hash`, missing snapshot files, missing `uri`, seed `retrieval` fields,
  raw `collected_at`/`published_at`/publisher/author declarations, and (when `evidence/catalog/catalog.ttl` exists) the catalog itself.
  `--shallow` skips the body comparison, `--no-catalog` skips the catalog.
  Existing evidence trees may report new findings.
- `convert` no longer sends already-Markdown or plain-text sources (GitHub `.md/.markdown/.txt/.rst`, local `.md/.txt`) through docling:
  docling silently dropped nested list items and some table sentences. Those sources are used as is, and docling is not needed for them.
  HTML, PDF and Office files still go through docling.
- `list --catalog` shows one row per document instead of one per chunk.

---
## v1.4.0 (2026-10-08) — SKOS concept profile and the source-agents domain in skb-ontology

### Changed (validation rules)

`skb-ontology validate` now has a SKOS concept profile. Existing Turtle that passed before may report new findings.

- **Provenance** [C5], [P1]: a concept may cite its source through a derived record
  (`dcterms:provenance` -> `prov:wasDerivedFrom`); a reified assertion may use `prov:wasDerivedFrom` instead of `prov:hadPrimarySource`.
- **Labels** [C8], [C9]: a concept needs at least one literal `skos:prefLabel`, at most one per language, and preferred
  labels must not repeat as alternative/hidden labels.
- **Migrated concepts** (identifier `concept:...`) [C10]-[C12]: need a `skos:scopeNote`, a declared `skos:ConceptScheme`,
  and an identifier equal to the IRI local name.
- **Names** [N3]/[N4]: individuals stay lowerCamelCase; concepts use domain-entity hyphen names.
- **Duplicates** [D1]: a label shared by several concepts is allowed (one label, many senses); duplicates among other terms still fail.
- **Hierarchy** [H1]: a cyclic `skos:broader`/`skos:narrower` chain is reported.
- Domain runs also read the `*.shapes.ttl` files that sit directly under the semantic root (KB-wide conventions).

### Added

- `skills/skb-ontology/references/domains/source-agents/`: a domain pack for observing sources: vocabulary, ontology,
  SHACL shapes and two SPARQL queries (current membership, effective trust). Publisher credibility and document diligence
  are separate factors and trust is derived, never stored. The pack ships no instances.
- `references/cross-graph-matching.md`.
- Tests: `test_skos_migration`, `test_source_agents_domain`, `test_source_agents_shapes`, `test_trust_factor_assessment`, `test_shapes_files_root`.

---
## v1.3.1 (2026-10-08) — Workflow TTL (`wf:`/`skbx:`) support in the public tooling

### Fixed

- The harness and router parsers only understood the legacy `msmwf:` vocabulary, so the `wf:`/`skbx:` workflow TTLs that
  shipped with PR #1 parsed to `id=None, tool=None` and could not be run, resolved, or checked. `workflow_ttl.py` (harness and
  router copies) now reads `wf:`/`skbx:` and still reads `msmwf:`. `resolve_workflow` finds a workflow by id by scanning
  `workflow-*.abox.ttl`, and `cc_check` no longer demands the removed `agent-context/workflow/index.ttl`.
- `cc_check` expects 7 core skills in `pack_config.json` (it required 8 before `skb-maintain` was removed in v1.3.0).

### Added

- `tests/test_workflow_v07.py` and `tests/test_public_workflows_parse.py`: the repository's own shipped workflows must parse,
  scan, and resolve by id.

### Known issue

- `agent-context/workflow/evidence/` holds two workflows with the id `evidence.graphify.etl`: the legacy `graphify-etl.abox.ttl`
  (restored for the older repository-setup tests) and `workflow-evidence-graphify-etl.abox.ttl`. `cc_check` reports the duplicate,
  and `test_cc_check_is_clean_on_the_shipped_tree` is marked `xfail(strict=True)` until one of them is retired.

---
## v1.3.0 (2026-10-08) — OWL reasoner, semantic search, skb-maintain dissolved

### Added

- `skb-graph-reasoning` 0.1.0: OWL 2 RL reasoner over canonical Turtle (`rdflib` + `owlrl`, no Java).
  `reason` writes a derived `<domain>/<name>.inferred.ttl` (with a `source-hash` header so `status` can tell fresh from stale),
  `check` reports logical inconsistencies, `stats` counts what is derived per kind, `query` runs SPARQL over the closure.
  Refuses to write when asserted TTL fails validation or the graph is inconsistent. Reflexive/standard-vocabulary noise is dropped,
  and `xsd:decimal`/`xsd:string` value-space clashes (same lexical form used as string and number) are reported as `xsd_artifacts`,
  not as inconsistencies.
- `skb-semantic-search` 0.1.0: semantic index and search over SKOS concepts and evidence chunks (EmbeddingGemma 2 + zvec).
  Metadata filters (`--uri`, `--uri-contains`, `--scheme`, `--status`), `--group-by-doc`, deprecated concepts excluded by default,
  and `status` (fresh/stale/missing from source fingerprints, model, dimension, partial builds).
- `skb-ontology orphans` and `skb-ontology stats` (read-only reports), `oracle/ontology_readiness.py`
  (score from TTL validity, orphans, evidence coverage, relation density, hub lock).
- `skb-evidence verify --orphans [--strict]`: also reports `evidence/md` notes that no seed references.
- `skb-explain/scripts/parent_alignment.py`: Markdown-projection parent-node scan, moved from `skb-maintain`.
- `tests/test_standalone_skb.py`: runs the CLIs and the harness from a copy of `skills/skb-*` only, with an empty `HOME`.

### Changed

- `skb-harness`: the oracle loader now also searches `<skills>/*/oracle/<name>.py` and passes only the arguments the function accepts.
  Before, oracles shipped by skills were never loaded and a missing oracle silently scored 1.0; the result now carries
  `details.warning` and `details.searched` so a vacuous PASS is visible. Skill lookup is
  `SKB_SKILL_<NAME>_HOME` (legacy alias `MSM_SKILL_<NAME>_HOME`) → sibling → `~/.claude/skills`, `~/.agents/skills`, `~/.gemini/config/skills` → legacy.
  The `skb-repository-setup` entrypoint is `scripts/skb` (legacy `scripts/msm` still accepted).
- `skb-ontology reason|materialize` now delegate to `skb-graph-reasoning reason`.
- The `maintain` workflows (`workflow-validation.abox.ttl`, legacy YAML, template) use `tool: skb-ontology`.

### Fixed

- `scripts/public_release_audit.sh` printed `PASS` without checking anything when `rg` was missing. It now fails if ripgrep is not installed,
  and CI installs it when the runner lacks it.
- `skb-evidence` could not be imported from the public tree: `scripts/layout.py` loads `skb-ontology/scripts/layout.py`,
  which v1.2.0 removed together with the legacy compiler. The module is restored.

### Removed

- `skb-maintain`. Its checks moved to their owners: orphans and statistics to `skb-ontology`, seed-less notes to
  `skb-evidence verify --orphans`, parent alignment to `skb-explain`. Its `rewrite` command only refused to apply changes,
  and its `drift` scan only called `skb-ontology validate`; both are gone.
- `skb-ontology/scripts/ttl_reason.py`, `ttl_materialize.py` (replaced by `skb-graph-reasoning`).

---
## v1.2.0 (2026-09-28) — Legacy compiler removal + guarded migration bridge

### Removed

- Legacy YAML(LinkML) → OWL compile → JSONL re-injection pipeline (22 scripts:
  `abox_compile`, `add`, `axiom`, `compile`, `completeness`, `definition`, `eca_run`,
  `eca_schedule`, `explain`, `gen_ddl`, `id_utils`, `layout`, `lint_iri`, `list`,
  `materialize`, `mece`, `ontology_mece_readiness`, `owl_postprocess`, `project_md`,
  `prov`, `rbox`, `reason`) and their 7 corresponding tests. TTL is now the only path;
  nothing in `scripts/` reads or writes YAML/JSONL ontology data.

### Added

- `scripts/migrate_legacy_to_ttl.py`, wired as `skb-ontology migrate-legacy`: a one-time
  bridge from a LinkML-style `classes`/`slots` definition YAML (optionally paired with an
  `instances` ABox YAML) into canonical Turtle. Dry-run by default; requires at least one
  `--evidence` IRI (forced onto every migrated term's `prov:hadPrimarySource`, since legacy
  YAML carries no provenance); validates the candidate graph against an isolated temp
  mirror through the real `ttl_validate.validate_target` gate before `--apply` ever writes
  to the real target.
- `tests/test_migrate_legacy_to_ttl.py` covering dry-run, `--apply`, missing-evidence
  rejection, and duplicate re-migration rejection.

---

## v1.1.1 (2026-09-13) — Public release boundary

- `skb-repository-setup`이 ontology JSONL 대신 유효한 domain Turtle을 생성하도록 변경.
- `skb-maintain`의 drift/orphan/analysis/oracle을 canonical Turtle 소비 경로로 변경.
- machine-specific workflow 절대경로 제거 및 공개 설치 URL 정렬.
- MIT license와 공개 배포 경계 문서화.

---

## v1.1.0 (2026-09-13) — SKB ontology TTL-only

- TBox, RBox, ABox, registry, provenance의 유일한 정본을 Turtle로 단일화.
- 활성 CLI를 direct TTL `add/list/validate/reason/materialize`로 교체.
- registry/link completeness, naming, case-fold IRI, identifier/label duplicate, SHACL gate 추가.
- 추론 산출물을 `*.inferred.jsonl` 대신 derived `*.inferred.ttl`로 변경.
- YAML/JSONL compile·projection·RBox authoring 명령은 활성 계약에서 폐기.

---

## v1.1.1 (2026-05-20)

> **거버넌스 정책 문서화: Concept HITL + Instance 차등 자동화.**
> v1.1.0 OI-E (ABox SPEC)의 사전 단계로 거버넌스 레이어 명시.

### Added — 거버넌스 정책

| 계층 | 정책 | 자동화 레벨 |
|------|------|---------|
| **Concept** | HITL / HITLFE 검수 필수 | 사람 승인 없이 자동 생성·수정 금지 |
| **Instance (상위 직접 연결)** | 관리 대상 (Human-supervised) | 수동 또는 검수 후 자동화 |
| **Instance (하위 간접 연결)** | 동적 자동화 (Self-healing) | 에이전트 자율 처리 |

**원칙**:
- Concept = 온톨로지 백본 (이론·정의) → 실수 시 구조 붕괴 → HITL 필수
- Instance 직접 연결 = 대표 사례 → 품질 보증 필요
- Instance 간접 연결 = 패턴화된 세부 사례 → 자동화 효율 우선

### Validation — 첫 적용 사례

- `concept__statistics` ↔ 6개 instance (descriptive/inferential/regression/bayesian/multivariate/time-series)
- `concept__gemini-family` ↔ 4개 instance (gemini-3-5-flash/pro/omni/spark)
- `concept__instance` (메타) — 기존 고아 파일 `instance__class.md`를 concept으로 재분류

### Documentation

- `docs/kb-directory-structure.md` — 거버넌스 오버레이 섹션 추가
- README MSM identity에 거버넌스 정책 한 줄 명시

### Deferred to v1.2.0

- Enforcement (skb-ontology HITL 가드, skb-maintain instance 티어 검증)
- ABox SPEC 본격 정의 (OI-E)

---

## v1.1.0 (2026-05-20)

> **Parent Node Alignment 내재화 + 4계층 KnowledgeBase 구조 도입.**
> MSM identity 재정의: Human-Agent KnowledgeBase Management System.

### Identity

- MSM = Human-Agent KnowledgeBase Management System (단순 Markdown scaffolding 도구가 아님)
- `ontology/`, `evidence/` 등 KB 전 구성 요소가 책임 범위

### Added — 결정사항 D-1 ~ D-7

| D# | 결정 |
|----|------|
| **D-1** | 부모 노드 명명: `{dir-name}__class.md` (구 `__hub.md`) |
| **D-2** | 단일 부모 원칙 (다중 도메인은 `cross_reference`) |
| **D-3** | 레벨 체계 L0~L4 권장, L5+ 자유 |
| **D-4** | 5축 분류(Model/Runtime/Reasoning/Action/Safety) 비강제 |
| **D-5** | `unclassified/` 디렉토리 운영 (분류 보류 entity) |
| **D-6** | TBox = 모두 Class / ABox = 모두 Instance |
| **D-7** | 4계층 KB 구조 — `ontology/{system,explain}` + `evidence/` |

### Added — 디렉토리 구조

- `ontology/explain/concept/` — TBox(구 `ontology/Tbox/`) 마이그레이션
- `ontology/explain/instance/` — ABox(구 `ontology/Abox/`) 마이그레이션
- `ontology/system/{semantic,kinetic,dynamic}/` — v1.2.0 작업 영역 placeholder
- 7개 신규 부모 anchor `__class.md` 생성

### Added — 스킬 명령

- `skb-ontology create-parent` — 부모 노드 자동 생성
- `skb-ontology add-belongs-to` — 자식 노드 belongs_to 일괄 추가
- `skb-ontology move-to-unclassified` — 미분류 디렉토리 격리
- `skb-maintain scan --kind parent-alignment` — 6규칙 검증
- `skb-maintain rewrite --kind parent-alignment` — 정합 회복 계획
- `skb-maintain analyze --view parent-tree` — 부모-자식 트리 시각화

### Changed

- `__hub.md` → `__class.md` 일괄 rename (106 파일)
- 자식 노드 frontmatter에 `belongs_to` 일괄 추가 (463 파일)
- `entities.jsonl` source_file 경로 동기화 (`Tbox/` → `explain/concept/`, `Abox/` → `explain/instance/`)
- 외부 markdown 181 파일의 wikilink 경로 자동 치환

### Migration Results

- 시작 위반: 626건
- 최종 위반: 0건 (실질) + L5+ deep_nesting 경고 (D-3 허용)
- 정합도: 100% (허용 경고 제외)

### Open Issues (v1.2.0 작업 대상)

- OI-A: `explain` ↔ `system` 매핑 관계 정의
- OI-B: `kinetic` vs `dynamic` 경계 — workflow 위치
- OI-C: 마이그레이션 시점 — `system/` 채우기 전략
- OI-D: `evidence` ↔ `ontology` backref 자동화
- OI-E: ABox SPEC — instance 명명·디렉토리 룰

### Documentation

- `docs/kb-directory-structure.md` v1.1.0으로 전면 재작성
- README MSM identity 및 4계층 구조 반영
- `planning/msm_v1.1.0/` — PRD, parent-alignment SPEC, ontology/maintain DELTA

---

## v1.0.1 (2026-05-20)

> Antigravity 플랫폼 지원 추가. Claude Code · Codex · Antigravity 세 플랫폼에서 일관된 스킬 설치 및 실행 가능.

### Added

- Antigravity 플랫폼 공식 지원
  - `install.sh --antigravity` — Antigravity 설치 옵션 추가
  - `install.sh --all` — 세 플랫폼 일괄 설치 (Claude Code + Codex + Antigravity)
  - `.antigravity/` 설정 디렉토리 추가

### Changed

- `install.sh`
  - 사용 문법 확대 (`--antigravity`, `--all` 옵션)
  - 타겟 플랫폼 경로 매핑 추가: `~/.gemini/antigravity/skills/` (Antigravity)

### Documentation

- README 플랫폼 지원 섹션 확대
- install.sh 코멘트 및 버전 번호 v1.0.1로 동기화

---

## v1.0.0 (2026-05-18)

> 5-Layer 아키텍처로 전면 재편. `.skill-modules/` 정책 폐지, v1.0.0 스킬 6개 승격, Graphify ETL 어댑터 추가.

### Breaking — 스킬 구조 재편

- `.skill-modules/` 디렉토리 정책 폐지 → 모든 스킬을 `skills/`로 통합
- v0.x 스킬 7개 (`msm-data-analysis`, `msm-kb-graph`, `msm-kb-rewrite`, `msm-mece-validator`, `msm-obsidian-cli`, `msm-ralph-etl`, `msm-rdf-owl-bridge`) 제거
- v1.0.0 스킬 6개 승격 (`skb-evidence`, `skb-harness`, `skb-maintain`, `skb-ontology`, `skb-orchestration`, `skb-repository-setup`)

### Added — 5-Layer 아키텍처

- `skb-repository-setup`: `skb init` — 5-Layer KB 디렉토리 골격 부트스트랩 (L0 score 1.0 검증 완료)
- `skb-harness`: memory 2-tier · L0~L3 런타임 · 5-Axis 계측 (비결정성·궤적·오라클·비용·HITL)
- `skb-orchestration` v1.0.0: 자연어 인텐트 라우팅 · CC 계약 · HITL 2층 정책 · workflow yaml 바인딩
- `skb-evidence`: URL/MD 수집 · 청킹 · dedup · seed 등록
- `skb-ontology`: entity·relation 생성 · MECE 검증 · Tbox/Abox 승격
- `skb-maintain`: scan · rewrite · data-analysis
- `workflow/evidence/graphify-etl.yaml`: Graphify ETL 워크플로우 정의

### Added — Graphify ETL 어댑터

- `skills/skb-evidence/scripts/graphify_to_skb.py`
  - Graphify `graph.json` → MSM entity/relation JSONL 변환 (Semantic Lifting Layer Option A)
  - `file_type == "concept"` 노드만 통과, `code` 타입 제거
  - god node (degree > mean + 2σ) → `tags: ["hub_candidate"]` 자동 태깅
  - Leiden `community_name` → `extra.leiden_community_name` 보존
  - LLM 재호출 없음 (Graphify Step 2 concept 노드 재활용)

---

## v0.2.0 (2026-04-28)

> 스킬 10개 → 7개 통합 재편 (md-* → msm-*). 각 스킬의 워크플로우 완결성을 높이고 구성을 간소화. mece-validator 완전 자동화, 보안 강화.

### Changed — 스킬 구조 재편
- `md-*` 10개 → `msm-*` 7개로 통합·리네임
  - `msm-kb-graph` (신규 통합): `md-graph-multihop` + `md-vector-search` + `md-scaffolding-design` 병합
    - 그래프 초기화·BFS 멀티홉·zvec 벡터 검색·인사이트 저장을 단일 진입점으로
  - `msm-ralph-etl`: `md-ralph-etl` + `md-frontmatter-rollup` 흡수 (ETL + 집계 통합)
  - `msm-mece-validator`, `msm-kb-rewrite`, `msm-rdf-owl-bridge`, `msm-obsidian-cli`, `msm-data-analysis`: 리네임
- README 스킬 구성 mermaid·역할 요약·의존관계 테이블 전면 갱신
- `graph_builder.py` `entities.*.dir` 레거시 포맷 호환 추가

### Added — mece-validator 자동화
- `msm-mece-validator/scripts/mece_interview.py`
  - `--auto` 플래그 — LLM이 인터뷰 답변 자동 생성, 무인 MECE 검증 루프
  - `--ollama` 플래그 — Ollama 확인 프롬프트 자동 수락, 로컬 모델 단독 실행
  - 질문 중복 조기 종료 — 반복 질문 감지 시 루프 자동 종료

### Security
- `skills/md-ralph-etl/data/ontology-entities/` (ETL 추출 엔티티 78개 파일) git 이력 전체 정화 (git filter-repo)
- `.gitignore`에 Ralph ETL 런타임 산출물 경로 추가 — archive/, data/ontology-entities/, data/ontology-relations/, evidence_corpus/

---

## v0.1.6 (2026-04-27)

> md-mece-validator 신규 스킬 추가. graph-ontology.yaml 온톨로지 설계·검증을 위한 Calibrated Validation 루프 구현.

### Added
- `md-mece-validator` 스킬 신규
  - `scripts/mece_interview.py` — MECE Calibrated Validation 루프 (light/medium/deep)
  - `references/depth-guide.md` — 채점 공식, 차원별 가중치, 출력 구조 상세
  - light: LLM 0회, heuristic 구조 체크 (클래스·관계 존재 여부, domain/range 선언)
  - medium: LLM 4-6회, ME/CE two-bucket 채점, 게이트 ≥0.75, crystallize
  - deep: LLM 15-24회, 6차원 채점 + Contrarian 체크, 게이트 ≥0.85 + open_questions 소진, `context/validation/mece-pack-{날짜}.yaml` 출력

### Changed
- `md-scaffolding-design/scripts/scaffold_project.py` `--mece [light|medium|deep]` 플래그 추가 — 분석 후 MECE 인터뷰 자동 연계
- `md-scaffolding-design/SKILL.md` 스크립트 목록에 `mece_interview.py` 추가, `md-mece-validator` 참조 링크 추가
- `requirements.txt` `anthropic>=0.40` 추가 (medium/deep 모드용)
- `docs/guides/ontology-config.md` MECE 검증 섹션 추가
- `docs/guides/kb-build-flows.md` Light 검증 기준에 `md-mece-validator` 참조 추가

---

## v0.1.5 (2026-04-25)

> md-obsidian-cli 스킬 구조 재설계, Obsidian 그래프 계층 패턴 명문화, md-ralph-etl PDF 처리 지원 추가, 스크립트 구문 오류 수정.

### Added
- `md-obsidian-cli/references/graph-hierarchy-patterns.md` 신규
  - Obsidian 그래프 계층 구조 설계 패턴 (L0/L1/L2 허브-리프 구조)
  - 폴더 레벨 가시성 규칙, 양방향 wikilink 패턴, frontmatter 계층 스키마
  - md-graph-multihop 연동 섹션 — `graph-config.yaml` `entity_dirs`·`relation_map` 설정 가이드
- `md-ralph-etl/scripts/step_pdf.py` 신규
  - arxiv 등 PDF URL 직접 처리 (opendataloader-pdf 우선, pymupdf4llm fallback)
  - 원본 `.pdf` + 변환본 `.md` 동시 저장
- `md-ralph-etl/scripts/ollama_http.py`, `publish_evidence.py` 신규

### Changed
- `md-obsidian-cli/SKILL.md` 네비게이션 허브로 재구조화 (~190줄 → ~45줄)
  - 중복 커맨드 레퍼런스 제거 (module.commands.md, cli-reference.md와 분리)
  - frontmatter description에 계층 구조 패턴 트리거 추가
- `md-obsidian-cli/references/graph-hierarchy-patterns.md` frontmatter 스키마 수정
  - `relations: [{type: parent_node}]` → `parent: "[[...]]"` 단일 필드로 통일
  - `md-scaffolding-design`의 `relation_map: {parent: child_of}` 와 직접 호환
- `md-ralph-etl/scripts/step_crawl.py` PDF URL 분기 추가
- `md-ralph-etl/scripts/ralph_cli.py` PDF 시나리오 지원 확장
- `md-scaffolding-design/SKILL.md` description 간소화

### Fixed
- `md-data-analysis/scripts/correlation_analysis.py` f-string 내 백슬래시 이스케이프 구문 오류 수정 (Python 3.11 이하 호환)

---

## v0.1.4 (2026-04-17)

> md-kb-rewrite의 wrapper layer 성격을 명확히 하고, semantic framing guardrail / H-X / ollama_mcp 운영 패턴을 README 차원에서 공식화한 릴리스.

### Added
- `md-kb-rewrite` 스킬에 semantic framing guardrail 추가
- H-X: interesting connection / missing synthesis 후보 탐지까지 범위 확대
- ollama_mcp 전용 섹션 README에 추가 — role, model(`qwen3.5:4b`), fallback, use patterns 명시

### Changed
- README 포지셔닝: GraphRAG/ETL 중심 → **structural layer + maintenance/governance layer** 구조 명시
- `md-kb-rewrite` 설명: rewrite loop 중심 → wrapper skill + semantic framing + synthesis detection로 확대
- `qwen3.5:4b`를 경량 보조 기본 모델로 문서화

---

## v0.1.3 (2026-04-07)

### Added
- `md-kb-rewrite` ��ų �ű� �߰� �� KB ��������/�Ź��ͽ� ����
  - 6�ܰ� rewrite loop (Detect �� Diagnose �� Draft �� Review �� Merge �� Observe)
  - H-A ~ H-G 7���� �޸���ƽ + H-X Connection Candidate
  - ollama_mcp �������� �ݺ� �۾�(H-B, H-F) Gemma ���� ����
- Workflow D (Raw��Wiki Compile) �� md-scaffolding-design�� �߰�
  - raw/ �ҽ� ������ ����ȭ�� wiki ���� ������
  - Karpathy LLM Knowledge Bases �λ���Ʈ ����
- H-X Connection Candidate �޸���ƽ �� ���� ���� �ռ� ��� �߰�

### Changed
- `md-scaffolding-design` �� KB �������� ������ md-kb-rewrite�� �и�
  - Workflow C ������ md-kb-rewrite ���𷺼����� ��ü
  - Workflow D ���� �߰�

### Integration
- ollama_mcp (���� Gemma4:e4b) ���� ���� �����ӿ�ũ �� ��ų ����

---

## v0.1.2
> KB ���� �帧(Top-Down / Bottom-Up)�� ����ȭ ��긯�� ������ ������.

| ���� ���� | ���� | v0.1.2 |
|-----------|------|--------|
| ���� ���� | �帧 ������ | **Top-Down / Bottom-Up** ���� ���� ���� + ���� ����ȭ |
| ��ū ����ȭ | ���� | **Light/Medium/Deep ���� ����** ��긯 + ���� ���� ���� |
| ���� �°� ���� | `�� validated` ���� ���� | `draft �� experimental �� validated` �ܰ躰 ���� �и� |
| ���� | `docs/guides/` 2�� | **`kb-build-flows.md` �߰�** �� �帧����긯������ Ż�� ���� |

��: [SPEC v0.1.2](../../planning/markdown-scaffolding-multihop_v0.1.2-SPEC.md)

---

## v0.1.1
> KB ���� ����(SPEC)�� �����ϰ�, Obsidian ��� ���� KB�� ���� ������ ������.

| ���� ���� | ���� | v0.1.1 |
|-----------|------|--------|
| KB ���� | `ontology/` �ȿ� domain ���� ȥ�� | **ABox/TBox �и�** �� `ontology/`(instance), `schema/`(type ����) |
| Obsidian ���� | `path:ontology/` �� relation ���� ȥ�� | `schema/` �и��� `path:ontology/` ���� ���ռ� Ȯ�� |
| Neo4j Ȯ�� | ���� ���� �۾� �ʿ� | `schema/relation/*.yaml` �� relationship type ���� ���� |
| docs ���� | ���� | `docs/index/ �� guides/ �� templates/` �ż� |
| ������ | `obsidian-vault` �� 5�� | **`kb-structure` ������ �߰�** �� ABox/TBox ��� �ڵ� ���� |

��: [SPEC v0.1.1](../../planning/markdown-scaffolding-multihop_v0.1.1-SPEC.md)
