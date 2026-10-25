#!/usr/bin/env python3
"""TBox 해석 평가용 정답 세트를 만든다. 질의 = 대체 라벨(altLabel) 또는 대표 라벨, 정답 = 그 요소의 IRI.

사용: make_alias_gold.py --tbox KB_TBOX_JSONL --out GOLD.jsonl
대체 라벨은 KB 작성자가 붙인 동의어다. 이 세트는 별칭 재현율을 재는 기준이며, 질문 문장 자체를 재는 것은 아니다.
"""
import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tbox", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.tbox, encoding="utf-8")]
    gold = []
    for r in rows:
        if not (r.get("pref_en") or r.get("pref_ko")):
            continue
        for alias in (r.get("alt") or [])[:1]:
            gold.append({"query": alias, "iri": r["iri"], "tkind": r["tkind"], "source": "alt"})
    Path(a.out).write_text("".join(json.dumps(g, ensure_ascii=False) + "\n" for g in gold), encoding="utf-8")
    print(f"gold={len(gold)} -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
