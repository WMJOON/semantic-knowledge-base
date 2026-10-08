#!/usr/bin/env python3
"""카탈로그 enricher — 도메인 전용 정보를 코어 어휘 밖의 확장 어휘로 싣는 플러그인.

코어 어휘(ec:)는 도메인을 모른다. enricher 는 (a) 문서 URL 에서 도출되는 속성, (b) 청크 본문에서 뽑는 위치(locators)를
돌려주는 순수 함수다. 네트워크·모델 없음, 같은 입력 → 같은 출력. 확장 어휘는 references/catalog/extensions/<name>.ttl.

enricher 모듈이 제공하는 것:
  NAME, NS(확장 네임스페이스), PREFIX
  enrich_source(url) -> {"title": str?, "props": {로컬이름: 값}, "issuer": str?}   (해당 없으면 {})
  chunk_heads(body) -> [위치 문자열]      청크 노트 안에서 머리로 시작하는 위치들(조문 머리 등)
  starts_with_head(body) -> bool         청크가 머리로 시작하는가(아니면 앞 청크에서 이어진 위치를 앞에 붙인다)
body 는 청크 노트 전체다(frontmatter 포함). 생성된 머리글(# 제목, > Source:)과 본문이 한 줄에 섞일 수 있어 둘을 가르지 않고,
첫 빈 줄 뒤 400자 창만 본다. 알려진 한계: 조문 머리가 400자 뒤에 처음 나오는 청크는 앞 청크의 조문이 이어진 것으로 본다.
"""
from __future__ import annotations

import re
import urllib.parse

# ── legal-kr: legalize-kr 미러(국가법령정보센터) 법령 문서 ─────────────────────────────
_LEGALIZE = "/legalize-kr/legalize-kr/"
_HEAD = re.compile(r"#{3,6}\s*(제\d+조(?:의\d+)?)")


class LegalKr:
    NAME = "legal-kr"
    PREFIX = "ecl"
    NS = "https://skb.dev/ontology/evidence-catalog/legal#"

    @staticmethod
    def enrich_source(url: str) -> dict:
        path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
        if _LEGALIZE not in path:
            return {}
        m = re.search(r"/kr/([^/]+)/([^/]+)\.md$", path)
        if not m:
            return {}
        props = {"lawName": m.group(1), "lawDocKind": m.group(2)}
        rev = re.search(r"/legalize-kr/legalize-kr/([0-9a-f]{40})/", path)
        if rev:  # 커밋으로 고정한 URL = 법령의 한 시점 버전(불변). main 브랜치 URL 은 시점이 바뀔 수 있어 싣지 않는다
            props["sourceRevision"] = rev.group(1)
        return {"title": f"{m.group(1)} {m.group(2)}", "props": props}

    @staticmethod
    def chunk_heads(body: str) -> list[str]:
        return _HEAD.findall(body)

    @staticmethod
    def starts_with_head(body: str) -> bool:
        tail = body.split("\n\n", 1)[-1][:400] or body[:400]
        return bool(re.search(r"#{3,6}\s*제\d+조", tail))


ENRICHERS = {LegalKr.NAME: LegalKr}


def get(name: str):
    if name not in ENRICHERS:
        raise SystemExit(f"알 수 없는 enricher: {name} (가능: {', '.join(sorted(ENRICHERS))})")
    return ENRICHERS[name]
