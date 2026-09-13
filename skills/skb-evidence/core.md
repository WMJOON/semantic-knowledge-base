# core — skb-evidence

## 1. 공통 프로토콜 (COLLECT / VERIFY / EVALUATE)

| 단계 | 책임 | 산출 |
|------|------|------|
| COLLECT | URI fetch → 텍스트 추출 → 청킹 → content-hash dedup → seed append | `evidence/seeds.jsonl`, `evidence/md/<slug>_<pad4>.md` |
| VERIFY | seeds.jsonl 읽기 → md_path 존재 확인 + content_hash 형식 검증 | exit 0/1 + 실패 목록 |
| EVALUATE | oracle score 계산 → trajectory에 `oracle_evaluation` 이벤트 | score ∈ [0,1] |

## 2. CLI

```bash
# dry-run (기본 — 파일 변경 없음)
scripts/skb-evidence collect --target ./my-kb --source https://example.com/doc

# 실제 수집
scripts/skb-evidence collect --target ./my-kb --source https://example.com/doc --apply

# 여러 소스
scripts/skb-evidence collect --target ./my-kb \
  --source https://example.com/a https://example.com/b \
  --apply --chunk-size 1200 --chunk-overlap 100

# 로컬 MD
scripts/skb-evidence collect --target ./my-kb --source ./notes/paper.md --apply

# file:// 로컬 HTML (테스트용)
scripts/skb-evidence collect --target ./my-kb --source file:///tmp/page.html --apply

# 검증
scripts/skb-evidence verify --target ./my-kb

# 목록
scripts/skb-evidence list --target ./my-kb

# 원문 스냅샷 캡처 포함 수집 (opt-in)
scripts/skb-evidence collect --target ./my-kb --source https://example.com/x --apply --capture

# 단독 캡처 (URL → PDF+PNG+HTML)
scripts/skb-evidence capture --url https://example.com/x --target ./my-kb
```

## 3. Slug 생성 규칙

| URI 종류 | Slug 파생 |
|----------|-----------|
| http/https | `hostname + path` 기반, 소문자, `[a-z0-9_]`만 유지, 최대 40자 |
| file:// | path의 basename (확장자 제외), 같은 정규화 |
| 로컬 파일 경로 | basename (확장자 제외), 같은 정규화 |

## 4. Chunking 알고리즘 (SPEC §5.1)

1. 문단 분리 (`\n\n+`)
2. 문단 > chunk_size → 문장 단위 분할 (`[.?!]\s+`)
3. 짧은 청크 (< 300 chars) → 인접 청크와 병합
4. 마지막 chunk_overlap 문자를 다음 청크 앞에 접합

단일 비분리 텍스트 → sliding-window: ⌈N / (chunk_size - chunk_overlap)⌉ 청크.

## 5. Dedup 규칙

- hash = `sha256(chunk_text)` — URI는 포함하지 않음
- 기존 seeds.jsonl에서 hash set 로드 → per-chunk 비교
- 중복 시: skip + trajectory에 `seed_dedup_skip` 이벤트

## 6. Generated Marker

| 파일 종류 | Marker |
|----------|--------|
| MD note | `<!-- msm:generated:file skill="skb-evidence" version="1.0.0" -->` |
| JSONL | (없음 — 모든 줄은 유효 JSON이어야 함) |

## 7. Oracle — evidence_seed_readiness

| 지표 | 계산 |
|------|------|
| URI 다양성 | unique URI 수 / 전체 seed 수 |
| 평균 청크 길이 적합성 | avg(chunk_length) ∈ [300, chunk_size] → 1.0, 아니면 0.0 |
| 모든 seed content_hash 존재 | 전체 OK → 1.0, 아니면 0.0 |
| MD 파일 존재 | 존재하는 md 수 / 전체 seed 수 |

Score = 4개 지표의 평균. Gate: ≥0.85 pass, ≥0.70 warn, <0.70 fail.

## 8. 산출 위치

| 경로 | 내용 |
|------|------|
| `evidence/seeds.jsonl` | seed 레코드 (append-only JSONL) |
| `evidence/md/<slug>_<pad4>.md` | 청크별 노트 |
| `evidence/captures/<sha12>.{pdf,png,html}` | 원문 스냅샷 (`--capture` 시에만, sha12=sha256(url)[:12]) |
| `harness/trajectory/run-<id>.jsonl` | 이벤트 로그 (run_id 있을 때) |

## 9. Source Snapshot Capture (v0.12.2, opt-in)

`--capture` 플래그(또는 `capture` 서브명령)로 URL 원문을 검증 시점에 박제한다. 휘발성
페이지(홈페이지·프로필)의 "그 시점에 그 내용이 있었다"를 사후 재검증 가능하게 한다.

- **엔진**: playwright(chromium). **lazy import** — `--capture` 없는 경로에서는 playwright/
  capture 모듈 자체를 import하지 않는다(코어 stdlib 경로 불변).
- **URL당 1회**: chunk 루프 이전 1회 캡처 → 같은 URI의 모든 chunk-seed가 동일 `snapshot` 참조.
- **graceful degrade**: playwright 부재·타임아웃·로드 실패 시 텍스트 수집은 계속하고
  `snapshot.status="error"` + actionable 메시지를 기록한다.
- **additive**: `snapshot`은 선택 필드. 부재 = 기존 seed. verify/oracle은 `.get()` 기반이라
  `snapshot` 유무에 영향받지 않는다(score 불변).

seed 스키마 추가 (선택):

```jsonc
"snapshot": {
  "pdf":  "evidence/captures/<sha12>.pdf",
  "png":  "evidence/captures/<sha12>.png",
  "html": "evidence/captures/<sha12>.html",
  "captured_at": "2026-06-02T03:42:17Z",   // UTC ISO-8601
  "status": "ok"                            // 실패 시 "error" + "error" 키
}
```

설치(캡처 사용 시에만): `pip install playwright && playwright install chromium`
