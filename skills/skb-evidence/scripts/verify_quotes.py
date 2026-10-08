#!/usr/bin/env python3
"""claims.json 의 fact quote 를 원문(evidence/raw)과 결정적으로 대조한다.

claims.json: [{"id", "type": "fact"|"inference", "raw", "quote", "basis": [...]}]
  fact       raw(원문 경로, --target 기준 상대) 안에 quote 가 글자 그대로 정확히 한 번 나와야 한다. 한 줄, 길이 제한.
  inference  quote 가 비어 있고, basis 는 실제 fact id 만 가리킨다.
검사 범위는 "근거 문장이 원문에 있는가"까지다. claim 이 quote 범위를 넘는지(의미 판정)는 하지 않는다:
그것은 작성자와 다른 검증자의 몫이다.

사용: verify_quotes.py --claims claims.json [--target KB] [--report report.md] [--min-len 40] [--max-len 250] [--json out.json]
종료 코드 0 = 문제 없음, 1 = 문제 있음.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def check_claims(claims: list, target: Path, min_len: int = 40, max_len: int = 250,
                 report_text: str | None = None) -> dict:
    issues: list[str] = []
    ids: set[str] = set()
    facts: dict[str, dict] = {}
    inferences: list[dict] = []
    raw_cache: dict[str, str | None] = {}
    for c in claims:
        cid = c.get("id") or "<no-id>"
        if cid in ids:
            issues.append(f"{cid}: id 중복")
        ids.add(cid)
        kind = c.get("type")
        if kind == "fact":
            facts[cid] = c
            raw = c.get("raw", "")
            if raw not in raw_cache:
                p = target / raw
                raw_cache[raw] = p.read_text(encoding="utf-8") if raw and p.is_file() else None
            text = raw_cache[raw]
            if text is None:
                issues.append(f"{cid}: raw 파일을 찾을 수 없음 ({raw!r})")
                continue
            q = c.get("quote", "")
            if "\n" in q:
                issues.append(f"{cid}: quote 가 여러 줄")
            if not min_len <= len(q) <= max_len:
                issues.append(f"{cid}: quote 길이 {len(q)} ({min_len}~{max_len} 아님)")
            n = text.count(q) if q else 0
            if n != 1:
                issues.append(f"{cid}: quote 가 원문에 {n}번 나옴(정확히 1번이어야 함)")
        elif kind == "inference":
            inferences.append(c)
        else:
            issues.append(f"{cid}: type 이 fact|inference 가 아님")
    for c in inferences:
        if c.get("quote"):
            issues.append(f"{c.get('id')}: inference 는 quote 가 비어 있어야 함")
        if not c.get("basis"):
            issues.append(f"{c.get('id')}: inference 에 basis 가 없음")
        for b in c.get("basis", []):
            if b not in facts:
                issues.append(f"{c.get('id')}: basis {b} 가 fact id 가 아님")
    uncited: list[str] = []
    if report_text is not None:
        cited = set(re.findall(r"\[([A-Za-z0-9][A-Za-z0-9_.-]*-\d{2,3})\]", report_text))
        missing = sorted(cited - ids)
        if missing:
            issues.append(f"보고서가 인용한 id 가 claims 에 없음: {missing[:6]}")
        uncited = sorted(set(facts) - cited)
    return {"facts": len(facts), "inferences": len(inferences), "uncited_facts": len(uncited), "issues": issues}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="verify-quotes")
    ap.add_argument("--claims", required=True, type=Path)
    ap.add_argument("--target", default=".", type=Path, help="raw 경로의 기준(KB root)")
    ap.add_argument("--report", type=Path, help="[claim-id] 로 인용하는 보고서 md(선택)")
    ap.add_argument("--min-len", type=int, default=40)
    ap.add_argument("--max-len", type=int, default=250)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    claims = json.loads(a.claims.read_text(encoding="utf-8"))
    report_text = a.report.read_text(encoding="utf-8") if a.report else None
    res = check_claims(claims, a.target.resolve(), a.min_len, a.max_len, report_text)
    print(f"fact {res['facts']} inference {res['inferences']} | 보고서 미인용 fact {res['uncited_facts']} | 문제 {len(res['issues'])}건")
    for i in res["issues"][:20]:
        print("  -", i, file=sys.stderr)
    if a.json:
        a.json.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if res["issues"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
