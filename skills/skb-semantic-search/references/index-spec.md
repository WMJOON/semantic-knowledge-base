# 인덱스 사양

## zvec 컬렉션

- 벡터 필드 `embedding`: FP32 768차원, HNSW, 코사인.
- doc id: `c000000`(concepts), `e000000`(evidence) 순번. zvec 이 `: / #` 등을 id 로 받지 않아 원래 식별자는 필드에 둔다.

| kind | 필드 |
|---|---|
| concepts | `iri`, `label`(`en / ko`), `status`, `scheme` |
| evidence | `seed_id`, `title`, `uri`, `md_path` |

## search_manifest.json

kind 별로 한 항목.

```json
{"concepts": {"model": "...", "dim": 768, "built_at": "ISO", "indexed": 1158, "skipped": 33,
              "limited": false, "source_fingerprint": "sha256", "seconds": 5.1}}
```

- `source_fingerprint`: concepts 는 `(상대경로, 파일 sha256)` 목록의 해시(`*.shapes.ttl`, `*.inferred.ttl` 제외), evidence 는 `seeds.jsonl` 의 sha256. **적재 시작 전에** 계산하므로 적재 도중 원천이 바뀌면 status 가 stale 이 된다.
- status 가 stale 인 이유: 원천 변경, 모델 변경, 차원 변경, `limited`(부분 적재).

## 개념 추출 JSONL (`kb_concepts.jsonl`)

한 줄에 개념 하나: `iri`, `pref_en[]`, `pref_ko[]`, `alt[]`, `scope_note`, `status`(`skb:status`/`ns2:status` 의 값 또는 빈 문자열), `scheme`, `file`. 중복 IRI 는 처음 나온 것만.
