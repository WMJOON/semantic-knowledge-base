#!/usr/bin/env python3
"""KB 의미 TTL 을 rdflib 그래프로 읽고 SELECT 쿼리 하나를 실행한다. 읽기 전용.

입력(stdin, JSON): {"target": "<KB 루트>", "query": "<SPARQL SELECT>"}
출력(stdout, JSON): {"vars": [...], "rows": [[...]], "failed": ["파싱 실패 파일 ..."]}
rdflib 가 있는 인터프리터로 실행한다(SKB_RDF_PYTHON). 검색 CLI 는 -I 로 돌아 사용자 site-packages 를 보지 않는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ss_sparql as S


def main() -> int:
    req = json.loads(sys.stdin.read())
    g, failed = S.load_graph(Path(req["target"]).resolve())
    res = S.run_select(g, req["query"])
    json.dump(dict(res, failed=failed), sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
