"""원문의 '제공자가 등록한 발행일'과 '발행 주체' 추출 (skb-evidence v1.1.4).

원칙
  - 제공자가 선언한 값만 쓴다. 본문 텍스트·URL·파일 수정 시각으로 추정하지 않는다.
  - 못 찾으면 값은 None, 이유는 'none:<사유>' 로 명시한다(빈칸으로 두지 않는다).
  - 반환: (value, source)
      value  : 'YYYY-MM-DD' 또는 UTC 'YYYY-MM-DDTHH:MM:SSZ' 또는 None
      source : 'meta:article:published_time' | 'jsonld:datePublished' | 'arxiv:citation_date' |
               'github-api:created_at' | 'hf-api:createdAt' | ... | 'none:no-declared-date' | 'none:fetch-error-403' ...

발행 주체(publisher)도 같은 원칙이다: 제공자가 선언한 값을 우선하고, 선언이 없어 URL 호스트로 대신할 때는
publisher_source 에 'domain-derived' 로 명시한다(선언된 값처럼 보이게 하지 않는다).
  publisher_source: jsonld:publisher | meta:og:site_name | meta:citation_publisher | meta:dc.publisher |
                    github-owner | hf-owner | platform-host | domain-derived

저자(authors)와 발행 주체 유형(publisher_type)도 같은 원칙이다. 저자·발행 주체·계정 유형은 **서로 섞지 않고 따로** 기록한다
(같은 소속이라도 발행 채널에 따라, 소속보다 개인의 입지가 더 큰 경우에 따라 무게가 다르다. 신뢰도 모델링은 이 수집 다음 단계다).
  authors            : [{"name", "type"(Person|Organization|null), "affiliation"(선언된 경우만), "account"}]
  authors_source     : jsonld:author | meta:citation_author | meta:author | github-api:user | none:no-declared-author
  publisher_type     : Organization | Person | unknown  (제공자가 선언한 경우만, 아니면 unknown)
  publisher_type_source: github-api:type | hf-api:overview | jsonld:publisher.@type | none:not-declared
  소속(affiliation)은 문서가 선언한 경우에만 적고, 소속으로 신뢰도를 추정하지 않는다.
  accounts           : 관찰된 플랫폼 계정 [{"platform","handle","id"(불변),"type","role"(publisher|author),"created_at","display_name",
                       "company","declared_bio","links","twitter","verified"(플랫폼이 선언한 경우만, 아니면 null),
                       "is_member_of_host_org"(플랫폼이 선언한 경우만),"source"}]
  accounts_source    : github-api | hf-api | none:no-platform-account
  document_type      : paper | unknown   (제공자가 선언한 학술 신호가 있을 때만 paper, 없으면 unknown — 블로그·문서 등으로 단정하지 않는다)
  document_type_source: meta:citation_* | jsonld:@type | platform-host | none:not-classified
  개인정보 최소화: 식별과 근거에 필요한 공개 프로필 값만 담는다(이메일·위치·팔로워 수 등은 담지 않는다).
  핸들은 바뀌거나 재사용되므로 키는 (platform, 불변 id) 이다.

수집일(collected_at)은 이 모듈이 아니라 convert 가 기록한다(수집 순간의 시각).
"""
from __future__ import annotations

import collections
import datetime as _dt
import functools
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

UA = "skb-evidence/1.1.4 (provenance-dates)"

# meta 이름(소문자) → 우선순위 순서. 제공자가 발행일로 선언한 표지만 쓴다.
_META_KEYS = [
    "article:published_time", "og:article:published_time", "og:published_time",
    "citation_publication_date", "citation_date", "dc.date.issued", "dcterms.issued",
    "dc.date", "dcterms.date", "dcterms.created", "dc.date.created", "publish_date", "pubdate", "date",
]


def normalize(raw: str | None) -> str | None:
    """제공자 값을 'YYYY-MM-DD' 또는 UTC ISO 로 정규화. 해석 못 하면 None."""
    if not raw:
        return None
    s = raw.strip()
    m = re.fullmatch(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return _dt.date(y, mo, d).isoformat()
        except ValueError:
            return None
    try:
        t = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        return t.date().isoformat() if (t.hour, t.minute, t.second) == (0, 0, 0) else t.isoformat()
    return t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Meta(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.multi: dict[str, list[str]] = collections.defaultdict(list)   # 같은 이름이 여러 번 나오는 meta(저자 등)
        self.jsonld: list[str] = []
        self._in_ld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content"):
                self.multi[key].append(a["content"])
                if key not in self.meta:
                    self.meta[key] = a["content"]
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_ld, self._buf = True, []
        elif tag == "time" and a.get("itemprop", "").lower() == "datepublished" and a.get("datetime"):
            self.meta.setdefault("itemprop:datepublished", a["datetime"])

    def handle_endtag(self, tag):
        if tag == "script" and self._in_ld:
            self._in_ld = False
            self.jsonld.append("".join(self._buf))

    def handle_data(self, data):
        if self._in_ld:
            self._buf.append(data)


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def parse_html(html: str) -> tuple[str | None, str]:
    """HTML 안의 제공자 선언 발행일. (value, source)"""
    p = _Meta()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001  깨진 HTML 은 '없음'으로 처리
        pass
    for blob in p.jsonld:
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        for node in _walk(data):
            v = normalize(node.get("datePublished") if isinstance(node.get("datePublished"), str) else None)
            if v:
                return v, "jsonld:datePublished"
    for key in _META_KEYS:
        v = normalize(p.meta.get(key))
        if v:
            return v, f"meta:{key}"
    v = normalize(p.meta.get("itemprop:datepublished"))
    if v:
        return v, "html:time[itemprop=datePublished]"
    return None, "none:no-declared-date"


def _get(url: str, timeout: int = 30, retries: int = 2) -> tuple[str | None, int | None]:
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json"})
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="replace"), 200
        except urllib.error.HTTPError as e:
            last = e.code
            if e.code == 429 and i < retries:
                time.sleep(5 * (i + 1)); continue
            return None, e.code
        except Exception:  # noqa: BLE001
            last = -1
    return None, last


def _github_created(url: str) -> tuple[str | None, str] | None:
    m = re.match(r"^https://github\.com/([^/]+)/([^/]+)/(issues|pull|discussions)/(\d+)", url)
    if not m:
        return None
    owner, repo, kind, num = m.groups()
    ep = {"issues": "issues", "pull": "pulls", "discussions": "discussions"}[kind]
    raw = None
    if shutil.which("gh"):
        r = subprocess.run(["gh", "api", f"repos/{owner}/{repo}/{ep}/{num}"], capture_output=True, text=True)
        raw = r.stdout if r.returncode == 0 else None
    if raw is None:
        raw, _ = _get(f"https://api.github.com/repos/{owner}/{repo}/{ep}/{num}")
    if raw:
        try:
            v = normalize(json.loads(raw).get("created_at"))
            if v:
                return v, "github-api:created_at"
        except ValueError:
            pass
    return None, "none:fetch-error-github-api"


def _hf_created(url: str) -> tuple[str | None, str] | None:
    m = re.match(r"^https://huggingface\.co/((?:datasets/|spaces/)?[^/]+/[^/]+)(/discussions/(\d+))?/?$", url)
    if not m or url.startswith("https://huggingface.co/docs") or url.startswith("https://huggingface.co/blog"):
        return None
    repo, _d, num = m.groups()
    kind = "datasets" if repo.startswith("datasets/") else "spaces" if repo.startswith("spaces/") else "models"
    repo = re.sub(r"^(datasets|spaces)/", "", repo)
    if num:
        raw, _ = _get(f"https://huggingface.co/api/{kind}/{repo}/discussions/{num}")
        try:
            v = normalize(json.loads(raw).get("createdAt")) if raw else None
        except ValueError:
            v = None
        return (v, "hf-api:discussion.createdAt") if v else (None, "none:fetch-error-hf-api")
    raw, _ = _get(f"https://huggingface.co/api/{kind}/{repo}")
    try:
        v = normalize(json.loads(raw).get("createdAt")) if raw else None
    except ValueError:
        v = None
    return (v, "hf-api:createdAt") if v else (None, "none:fetch-error-hf-api")


def extract_published(url: str, html: str | None = None, pace: float = 0.0) -> tuple[str | None, str]:
    """URL(과 이미 받아 둔 HTML)에서 제공자 선언 발행일을 찾는다."""
    if not url.startswith(("http://", "https://")):
        return None, "none:local-file"
    if re.match(r"^https://(raw\.githubusercontent\.com|github\.com/[^/]+/[^/]+/(blob|tree)/)", url) or \
            re.fullmatch(r"https://github\.com/[^/]+/[^/]+/?", url):
        return None, "none:no-declared-date"          # 파일·저장소 루트는 발행일이 없다(커밋 시각은 발행일이 아니다)
    for fn in (_github_created, _hf_created):
        r = fn(url)
        if r is not None:
            return r
    m = re.match(r"^https?://arxiv\.org/(?:abs|pdf|html)/([0-9]{4}\.[0-9]{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/[0-9]{7})(?:v\d+)?(?:\.pdf)?/?$", url)
    if m:
        if pace:
            time.sleep(pace)
        page, code = _get(f"https://arxiv.org/abs/{m.group(1)}")
        if page is None:
            return None, f"none:fetch-error-{code}"
        v, src = parse_html(page)
        return (v, "arxiv:" + src.split(":", 1)[-1]) if v else (None, src)
    if html is None:
        html, code = _get(url)
        if html is None:
            return None, f"none:fetch-error-{code}"
    return parse_html(html)


# ----------------------------------------------------------------------------------------------
# 발행 주체
# ----------------------------------------------------------------------------------------------
_PUB_META = ["citation_publisher", "dc.publisher", "dcterms.publisher", "og:site_name", "application-name"]
_PUB_META_ORDER = ["og:site_name", "citation_publisher", "dc.publisher", "dcterms.publisher"]


def _clean(name) -> str | None:
    if not isinstance(name, str):
        return None
    n = re.sub(r"\s+", " ", name).strip()
    return n or None


def parse_publisher(html: str) -> tuple[str | None, str]:
    """HTML 안의 제공자 선언 발행 주체. JSON-LD publisher > og:site_name > citation_publisher > dc.publisher."""
    p = _Meta()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001
        pass
    for blob in p.jsonld:
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        for node in _walk(data):
            pub = node.get("publisher")
            name = _clean(pub) if isinstance(pub, str) else _clean(pub.get("name")) if isinstance(pub, dict) else None
            if name:
                return name, "jsonld:publisher"
    for key in _PUB_META_ORDER:
        name = _clean(p.meta.get(key))
        if name:
            return name, f"meta:{key}"
    return None, "none:no-declared-publisher"


def _host(url: str) -> str:
    from urllib.parse import urlparse
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def extract_publisher(url: str, html: str | None = None) -> tuple[str, str]:
    """발행 주체. 항상 값을 돌려준다: 선언된 값 > 계정 소유자 > 플랫폼 > 호스트명(domain-derived)."""
    if not url.startswith(("http://", "https://")):
        return "local", "local-file"
    m = re.match(r"^https://(?:raw\.githubusercontent\.com|github\.com)/([^/]+)/", url)
    if m:
        return m.group(1), "github-owner"
    m = re.match(r"^https://huggingface\.co/(?!docs|blog|papers|learn)((?:datasets/|spaces/)?)([^/]+)/[^/]+", url)
    if m:
        return m.group(2), "hf-owner"
    if _host(url) == "huggingface.co":
        return "Hugging Face", "platform-host"
    if _host(url) == "arxiv.org":
        return "arXiv", "platform-host"
    if html:
        name, src = parse_publisher(html)
        if name:
            return name, src
    return _host(url), "domain-derived"


def extract_all(url: str, html: str | None = None, pace: float = 0.0) -> dict:
    """발행일·발행 주체·저자·발행 주체 유형을 한 번의 HTML 수집으로 함께 구한다."""
    who, who_src = extract_publisher(url, html)
    am = re.match(r"^https?://arxiv\.org/(?:abs|pdf|html)/([0-9]{4}\.[0-9]{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/[0-9]{7})", url)
    if am:                                        # arXiv: 초록 페이지 한 번으로 발행일과 저자를 모두 읽는다(요청 간격 준수)
        if pace:
            time.sleep(pace)
        page, code = _get(f"https://arxiv.org/abs/{am.group(1)}")
        if page is None:
            pub, pub_src, authors, authors_src = None, f"none:fetch-error-{code}", [], f"none:fetch-error-{code}"
        else:
            pub, src = parse_html(page)
            pub, pub_src = (pub, "arxiv:" + src.split(":", 1)[-1]) if pub else (None, src)
            authors, authors_src = parse_authors(page)
            html = page                                   # 문서 유형 판별에 재사용
    else:
        # HF 는 토론(API 로 저자를 얻는다)만 제외하고, 모델 카드·블로그·문서 페이지는 HTML 을 받아 저자 표기를 읽는다.
        generic = url.startswith(("http://", "https://")) and not re.match(
            r"^https?://(raw\.githubusercontent\.com|github\.com)/", url) and not re.match(
            r"^https://huggingface\.co/(?:datasets/|spaces/)?[^/]+/[^/]+/discussions/\d+", url)
        fetch_err = None
        if generic and html is None:
            html, code = _get(url)
            if html is None:
                fetch_err = f"none:fetch-error-{code}"
        pub, pub_src = (None, fetch_err) if fetch_err else extract_published(url, html, pace)
        authors, authors_src = ([], fetch_err) if fetch_err else extract_authors(url, html)
        who, who_src = extract_publisher(url, html)
    ptype, ptype_src = extract_publisher_type(url, html, who_src)
    accounts, accounts_src = extract_accounts(url, authors, who_src)
    dtype, dtype_src = classify_document(url, html)
    return {"published_at": pub, "published_at_source": pub_src, "publisher": who, "publisher_source": who_src,
            "authors": authors, "authors_source": authors_src, "publisher_type": ptype, "publisher_type_source": ptype_src,
            "accounts": accounts, "accounts_source": accounts_src,
            "document_type": dtype, "document_type_source": dtype_src}


# ----------------------------------------------------------------------------------------------
# 저자 · 발행 주체 유형 (제공자 선언값만)
# ----------------------------------------------------------------------------------------------
_TYPE_MAP = {"person": "Person", "organization": "Organization", "corporation": "Organization", "newsmediaorganization": "Organization",
             "educationalorganization": "Organization", "ngo": "Organization", "governmentorganization": "Organization"}


def _norm_type(t) -> str | None:
    if isinstance(t, list):
        t = next((x for x in t if isinstance(x, str) and x.lower() in _TYPE_MAP), None)
    return _TYPE_MAP.get(t.lower()) if isinstance(t, str) else None


def _aff_name(a) -> str | None:
    if isinstance(a, list):
        a = a[0] if a else None
    if isinstance(a, dict):
        a = a.get("name")
    return _clean(a)


def _author_from_node(n) -> dict | None:
    if isinstance(n, str):
        name = _clean(n)
        return {"name": name, "type": None, "affiliation": None, "account": None} if name else None
    if isinstance(n, dict):
        name = _clean(n.get("name"))
        if not name:
            return None
        return {"name": name, "type": _norm_type(n.get("@type")),
                "affiliation": _aff_name(n.get("affiliation") or n.get("worksFor")), "account": None}
    return None


def parse_authors(html: str) -> tuple[list[dict], str]:
    """HTML 안의 제공자 선언 저자. JSON-LD author > citation_author > author/article:author/dc.creator."""
    p = _Meta()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001
        pass
    for blob in p.jsonld:
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        for node in _walk(data):
            raw = node.get("author")
            if raw is None:
                continue
            items = raw if isinstance(raw, list) else [raw]
            out = [a for a in (_author_from_node(i) for i in items) if a]
            if out:
                return out, "jsonld:author"
    names = [_clean(x) for x in p.multi.get("citation_author", [])]
    names = [n for n in names if n]
    if names:
        inst = [_clean(x) for x in p.multi.get("citation_author_institution", [])]
        aligned = len(inst) == len(names)          # 개수가 같을 때만 순서대로 대응(어긋나면 소속은 버린다)
        return [{"name": n, "type": None, "affiliation": inst[i] if aligned else None, "account": None}
                for i, n in enumerate(names)], "meta:citation_author"
    for key in ("author", "article:author", "dc.creator", "dcterms.creator"):
        vals = [_clean(x) for x in p.multi.get(key, []) if _clean(x)]
        vals = [v for v in vals if not v.startswith(("http://", "https://"))]     # article:author 가 프로필 URL 인 경우 제외
        if vals:
            return [{"name": v, "type": None, "affiliation": None, "account": None} for v in vals], f"meta:{key}"
    return [], "none:no-declared-author"


@functools.lru_cache(maxsize=512)
def _github_json(path: str) -> dict | None:
    raw = None
    if shutil.which("gh"):
        r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
        raw = r.stdout if r.returncode == 0 else None
    if raw is None:
        raw, _ = _get(f"https://api.github.com/{path}")
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def _github_author(url: str) -> tuple[list[dict], str] | None:
    m = re.match(r"^https://github\.com/([^/]+)/([^/]+)/(issues|pull|discussions)/(\d+)", url)
    if not m:
        return None
    owner, repo, kind, num = m.groups()
    d = _github_json(f"repos/{owner}/{repo}/{ {'issues': 'issues', 'pull': 'pulls', 'discussions': 'discussions'}[kind] }/{num}")
    u = (d or {}).get("user") or {}
    if u.get("login"):
        t = {"user": "Person", "organization": "Organization"}.get(str(u.get("type", "")).lower())
        return [{"name": u["login"], "type": t, "affiliation": None, "account": u["login"]}], "github-api:user"
    return [], "none:fetch-error-github-api"


@functools.lru_cache(maxsize=512)
def _github_owner_type(owner: str) -> str | None:
    d = _github_json(f"users/{owner}")
    return {"user": "Person", "organization": "Organization"}.get(str((d or {}).get("type", "")).lower())


@functools.lru_cache(maxsize=512)
def _hf_owner_type(owner: str) -> str | None:
    for kind, label in (("organizations", "Organization"), ("users", "Person")):
        raw, code = _get(f"https://huggingface.co/api/{kind}/{owner}/overview")
        if raw is not None and code == 200:
            return label
    return None


def extract_publisher_type(url: str, html: str | None, publisher_source: str) -> tuple[str, str]:
    """발행 주체가 조직인지 사람인지: 제공자가 선언한 경우만. 아니면 ('unknown', 'none:not-declared')."""
    if publisher_source == "github-owner":
        m = re.match(r"^https://(?:raw\.githubusercontent\.com|github\.com)/([^/]+)/", url)
        t = _github_owner_type(m.group(1)) if m else None
        return (t, "github-api:type") if t else ("unknown", "none:fetch-error-github-api")
    if publisher_source == "hf-owner":
        m = re.match(r"^https://huggingface\.co/(?:datasets/|spaces/)?([^/]+)/", url)
        t = _hf_owner_type(m.group(1)) if m else None
        return (t, "hf-api:overview") if t else ("unknown", "none:fetch-error-hf-api")
    if publisher_source == "jsonld:publisher" and html:
        p = _Meta()
        try:
            p.feed(html)
        except Exception:  # noqa: BLE001
            pass
        for blob in p.jsonld:
            try:
                data = json.loads(blob)
            except ValueError:
                continue
            for node in _walk(data):
                pub = node.get("publisher")
                t = _norm_type(pub.get("@type")) if isinstance(pub, dict) else None
                if t:
                    return t, "jsonld:publisher.@type"
    return "unknown", "none:not-declared"


def extract_authors(url: str, html: str | None) -> tuple[list[dict], str]:
    if not url.startswith(("http://", "https://")):
        return [], "none:local-file"
    hd = hf_discussion_author(url) if url.startswith("https://huggingface.co/") else None
    if hd:
        return [{"name": hd["handle"], "type": hd["type"], "affiliation": None, "account": hd["handle"]}], "hf-api:discussion.author"
    gh = _github_author(url)
    if gh is not None:
        return gh
    if re.match(r"^https://(raw\.githubusercontent\.com|github\.com)/", url):
        return [], "none:no-declared-author"           # 파일·저장소·문서 페이지에는 저자가 선언돼 있지 않다
    if html:
        return parse_authors(html)
    return [], "none:no-html"


# ----------------------------------------------------------------------------------------------
# 플랫폼 계정 사실 (제공자 선언값, 개인정보 최소화)
# ----------------------------------------------------------------------------------------------
_BIO_MAX = 300


@functools.lru_cache(maxsize=512)
def _hf_json(path: str) -> dict | None:
    raw, _code = _get(f"https://huggingface.co/api/{path}")
    try:
        d = json.loads(raw) if raw else None
    except ValueError:
        return None
    return d if isinstance(d, dict) and not d.get("error") else None


def _trim(text) -> str | None:
    t = _clean(text)
    return t[:_BIO_MAX] if t else None


@functools.lru_cache(maxsize=512)
def github_account(login: str) -> dict | None:
    u = _github_json(f"users/{login}")
    if not u or not u.get("login"):
        return None
    typ = {"user": "Person", "organization": "Organization"}.get(str(u.get("type", "")).lower())
    verified = None
    if typ == "Organization":
        o = _github_json(f"orgs/{login}")
        if isinstance(o, dict) and isinstance(o.get("is_verified"), bool):
            verified = o["is_verified"]                       # 플랫폼이 선언한 조직 인증 표시
    blog = _clean(u.get("blog"))
    if blog and not blog.startswith(("http://", "https://")):
        blog = "https://" + blog
    return {"platform": "github", "handle": u["login"], "id": u.get("id"), "type": typ,
            "created_at": normalize(u.get("created_at")), "display_name": _clean(u.get("name")),
            "company": _clean(u.get("company")), "declared_bio": _trim(u.get("bio")),
            "links": [blog] if blog else [], "twitter": _clean(u.get("twitter_username")),
            "verified": verified, "is_member_of_host_org": None, "source": "github-api:users"}


@functools.lru_cache(maxsize=512)
def hf_account(owner: str) -> dict | None:
    d = _hf_json(f"organizations/{owner}/overview")
    if d and d.get("name"):
        return {"platform": "huggingface", "handle": d["name"], "id": d.get("_id"), "type": "Organization", "created_at": None,
                "display_name": _clean(d.get("fullname")), "company": None, "declared_bio": _trim(d.get("details")),
                "links": [], "twitter": None,
                "verified": d["isVerified"] if isinstance(d.get("isVerified"), bool) else None,
                "is_member_of_host_org": None, "source": "hf-api:overview"}
    d = _hf_json(f"users/{owner}/overview")
    if d and (d.get("user") or d.get("name")):
        return {"platform": "huggingface", "handle": d.get("user") or d.get("name"), "id": d.get("_id"), "type": "Person",
                "created_at": normalize(d.get("createdAt")), "display_name": _clean(d.get("fullname")), "company": None,
                "declared_bio": _trim(d.get("details")), "links": [], "twitter": None, "verified": None,
                "is_member_of_host_org": None, "source": "hf-api:overview"}
    return None


def _hf_discussion(url: str) -> dict | None:
    m = re.match(r"^https://huggingface\.co/((?:datasets/|spaces/)?[^/]+/[^/]+)/discussions/(\d+)", url)
    if not m:
        return None
    repo, num = m.groups()
    kind = "datasets" if repo.startswith("datasets/") else "spaces" if repo.startswith("spaces/") else "models"
    return _hf_json(f"{kind}/{re.sub(r'^(datasets|spaces)/', '', repo)}/discussions/{num}")


def hf_discussion_author(url: str) -> dict | None:
    d = _hf_discussion(url)
    if not d:
        return None
    a = d.get("author") or {}
    if not a.get("name"):
        return None
    ev = (d.get("events") or [{}])[0].get("author") or {}
    member = ev.get("isOrgMember") if isinstance(ev.get("isOrgMember"), bool) else None
    typ = {"user": "Person", "org": "Organization"}.get(str(a.get("type", "")).lower())
    return {"platform": "huggingface", "handle": a["name"], "id": a.get("_id"), "type": typ, "created_at": None,
            "display_name": _clean(a.get("fullname")), "company": None, "declared_bio": None, "links": [], "twitter": None,
            "verified": None, "is_member_of_host_org": member, "source": "hf-api:discussion.author"}


def extract_accounts(url: str, authors: list[dict], publisher_source: str) -> tuple[list[dict], str]:
    """관찰된 플랫폼 계정: 발행 주체 계정(role=publisher)과 저자 계정(role=author). 선언값만."""
    out: list[dict] = []
    seen: set = set()

    def add(acct: dict | None, role: str) -> None:
        if acct and (acct["platform"], acct["handle"], role) not in seen:
            seen.add((acct["platform"], acct["handle"], role)); out.append({**acct, "role": role})

    if publisher_source == "github-owner":
        m = re.match(r"^https://(?:raw\.githubusercontent\.com|github\.com)/([^/]+)/", url)
        add(github_account(m.group(1)) if m else None, "publisher")
    elif publisher_source == "hf-owner":
        m = re.match(r"^https://huggingface\.co/(?:datasets/|spaces/)?([^/]+)/", url)
        add(hf_account(m.group(1)) if m else None, "publisher")
    for a in authors:
        if a.get("account") and url.startswith("https://github.com/"):
            add(github_account(a["account"]), "author")
    hd = hf_discussion_author(url) if url.startswith("https://huggingface.co/") else None
    if hd:
        full = hf_account(hd["handle"])                       # 작성자 프로필(자기소개 등)이 있으면 합친다
        add({**(full or hd), "is_member_of_host_org": hd["is_member_of_host_org"], "source": hd["source"]}, "author")
    return out, ("none:no-platform-account" if not out else "+".join(sorted({o["source"].split(":")[0] for o in out})))


# ----------------------------------------------------------------------------------------------
# 문서 유형 (신뢰도 기본값의 입력. 제공자가 선언한 학술 신호가 있을 때만 'paper')
# ----------------------------------------------------------------------------------------------
_PREPRINT_HOSTS = ("arxiv.org", "medrxiv.org", "biorxiv.org", "ssrn.com", "openreview.net")
_SCHOLARLY_META = ("citation_journal_title", "citation_conference_title", "citation_doi", "citation_arxiv_id",
                   "citation_pdf_url", "citation_publication_date")


def classify_document(url: str, html: str | None) -> tuple[str, str]:
    """('paper'|'unknown', source). 선언된 학술 신호만 쓴다. 신호가 없으면 다른 유형으로 단정하지 않고 unknown."""
    if not url.startswith(("http://", "https://")):
        return "unknown", "none:not-classified"
    if html:
        p = _Meta()
        try:
            p.feed(html)
        except Exception:  # noqa: BLE001
            pass
        for blob in p.jsonld:
            try:
                data = json.loads(blob)
            except ValueError:
                continue
            for node in _walk(data):
                t = node.get("@type")
                types = t if isinstance(t, list) else [t]
                if any(isinstance(x, str) and x.lower() in ("scholarlyarticle", "medicalscholarlyarticle") for x in types):
                    return "paper", "jsonld:@type"
        if p.multi.get("citation_title") and any(p.multi.get(k) for k in _SCHOLARLY_META):
            return "paper", "meta:citation_*"
    if _host(url) in _PREPRINT_HOSTS or any(_host(url).endswith("." + h) for h in _PREPRINT_HOSTS):
        return "paper", "platform-host"
    return "unknown", "none:not-classified"
