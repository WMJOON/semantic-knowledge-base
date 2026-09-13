# core — skb-record-archive

## 1. 공통 프로토콜 (DESIGN / EXECUTE / EVALUATE)

| 단계 | 책임 | 산출 |
|------|------|------|
| DESIGN | target 경로 검증, schema DDL 로드, contract validate | plan JSON |
| EXECUTE | dry-run / apply 분기. SQLite insert 또는 DuckDB query | result JSON, trajectory log |
| EVALUATE | row count, ECA 발동 건수, snapshot 크기 | `instance_op_result` 이벤트 |

## 2. 저장소 구조

```
<target>/record-archive/
  registry/
    instance-ids.jsonl # stable id + type/source_refs registry
  runtime/
    runtime.db        # SQLite WAL — OLTP 상태 기억
  events/
    *.jsonl           # append-only occurrence/change events
  derived/
    *.jsonl           # materialized derived state records
  snapshots/
    YYYYMMDD_HHMMSS.parquet   # DuckDB analytics bridge
  schema/
    init.sql          # 최초 DDL (skb-ontology gen-ddl 산출물 소비)
    migrate_v*.sql    # 버전별 마이그레이션
```

## 3. CLI

```bash
# DB 초기화 (dry-run)
scripts/skb-record-archive init --target ./my-kb

# DB 초기화 (실제 생성)
scripts/skb-record-archive init --target ./my-kb --apply

# row 삽입 (contract validate → insert)
scripts/skb-record-archive insert \
  --target ./my-kb --table market_signal \
  --data '{"signal_id":"s001","value":0.85}' --apply

# DuckDB analytics 쿼리
scripts/skb-record-archive query \
  --target ./my-kb \
  --sql "SELECT * FROM read_parquet('record-archive/snapshots/*.parquet') LIMIT 10"

# parquet 스냅샷 내보내기
scripts/skb-record-archive export-snapshot --target ./my-kb --apply

# ECA 규칙 실행
scripts/skb-record-archive eca-run \
  --target ./my-kb --table market_signal \
  --row '{"signal_id":"s001","value":0.85}'

# schema 마이그레이션
scripts/skb-record-archive migrate --target ./my-kb --to v0.11 --apply
```

## 4. HITL 정책

Always HITL:
- 기존 runtime.db schema 파괴적 변경 (DROP TABLE, ALTER 열 삭제)
- migrate --to 버전 다운그레이드

No HITL:
- dry-run, query, export-snapshot
- 빈 DB init
- row insert (contract validate 통과 시)

## 5. ECA 규칙 실행 흐름

```
row INSERT
  → contract_validate (skb-ontology 계약 준수 확인)
  → eca_runner: Event 탐지 → Condition 평가 → Action 실행
  → trajectory log (event_type: eca_fired / eca_skip)
```

ECA 규칙 정의는 `ontology/system/kinetic/{domain}.ttl`의 transition/action rule graph에서 로드한다.

## 6. export-snapshot 흐름

```
runtime.db (SQLite)
  → SELECT * FROM <table>  →  pandas / duckdb  →  parquet
  → record-archive/snapshots/YYYYMMDD_HHMMSS.parquet
```

스냅샷은 `skb-explain`의 입력 소스다.

## 7. Open Items

- full ECA rule engine (현재 skeleton)
- parquet → DuckDB persistent catalog 연동
- snapshot retention 정책 (TTL / 최대 N개)

## 8. 시간축 정책

`created_at`은 새 스키마에서 피한다. source, observation, archive, domain,
derivation 관점이 서로 다르기 때문이다.

| 필드 | 의미 |
|------|------|
| `published_at` | 원천이 주장하는 발행·공개 시각 |
| `observed_at` | SKB이 해당 원천 내용을 처음 관측한 시각 |
| `captured_at` | 검증 스냅샷을 박제한 시각 |
| `archived_at` | `record-archive/`에 append된 시각 |
| `valid_at` / `effective_at` | 도메인 안에서 fact/state가 성립하는 시각 |
| `derived_at` | kinetic rule 또는 query로 도출값을 계산한 시각 |
