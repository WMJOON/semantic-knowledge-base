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

## v0.3.0: tbox 색인과 키워드 텍스트

- 원천: 의미 TTL 의 `owl:Class`, `rdfs:Class`, `owl:ObjectProperty`, `owl:DatatypeProperty`. 추출 결과는 `kb_tbox.jsonl`(tkind, pref_en, pref_ko, alt, hidden, note, domain, range, super).
- 필드(zvec): `iri`, `label`, `tkind`, `domain`, `range`, `super`. 다중 값은 공백으로 잇는다.
- 키워드 색인: `texts_<kind>.jsonl` 한 줄 = `{id, iri, label, status?, scheme?, alt, hidden, note, ...}`. concepts 와 tbox 만 만든다. id 는 zvec 문서 id 와 같다.
- 신선도: tbox 의 지문은 concepts 와 같은 의미 TTL 파일 지문을 쓴다.
- 기존 concepts 색인은 키워드 텍스트 파일이 없으므로, 하이브리드를 쓰려면 `index concepts` 를 다시 실행한다. 없으면 벡터만 쓰고 경고를 낸다.

