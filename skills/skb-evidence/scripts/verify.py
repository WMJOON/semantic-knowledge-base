#!/usr/bin/env python3
"""Verify seeds.jsonl: check md_path files exist + content_hash format,
and that every evidence/raw document carries its collection date (collected_at) and publication-date status.

Exit 0 if all seeds pass; exit 1 if any fail.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as _layout_mod  # noqa: E402
import retrieval_meta as _rm  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="verify")
    p.add_argument("--target", default=".", help="KB root path")
    p.add_argument("--id", default=None, help="Verify single seed by id")
    p.add_argument("--shallow", action="store_true", help="본문-해시 대조를 건너뛴다(대형 KB 빠른 점검)")
    p.add_argument("--no-catalog", action="store_true", help="카탈로그(catalog.ttl)가 있어도 검증하지 않는다")
    p.add_argument("--orphans", action="store_true", help="seeds.jsonl 이 가리키지 않는 evidence/md 노트를 경고로 보고한다(반대 방향 점검)")
    p.add_argument("--strict", action="store_true", help="--orphans 결과를 경고가 아니라 실패로 취급한다")
    return p.parse_args(argv)


_ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_PUB = re.compile(r"^(unavailable|\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?)$")


def _raw_date_failures(raw_dir: Path) -> list[str]:
    """원문 frontmatter 의 collected_at(필수, UTC ISO), published_at(값 또는 unavailable), published_at_source."""
    out: list[str] = []
    if not raw_dir.is_dir():
        return out
    for p in sorted(raw_dir.glob("*.md")):
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        fm = {k.strip(): v.strip() for k, _, v in (ln.partition(":") for ln in (m.group(1).splitlines() if m else []))}
        if not _ISO_Z.match(fm.get("collected_at", "")):
            out.append(f"raw:{p.name}: collected_at 누락 또는 형식 오류 ({fm.get('collected_at')!r})")
        if not _PUB.match(fm.get("published_at", "")):
            out.append(f"raw:{p.name}: published_at 누락 또는 형식 오류 ({fm.get('published_at')!r}; 값이 없으면 'unavailable')")
        if not fm.get("published_at_source"):
            out.append(f"raw:{p.name}: published_at_source 누락(발행일 출처 또는 none:<사유>)")
        if not fm.get("publisher"):
            out.append(f"raw:{p.name}: publisher(발행 주체) 누락")
        if not fm.get("publisher_source"):
            out.append(f"raw:{p.name}: publisher_source 누락(선언 출처 또는 domain-derived)")
        if fm.get("publisher_type") not in ("Organization", "Person", "unknown"):
            out.append(f"raw:{p.name}: publisher_type 누락 또는 값 오류 ({fm.get('publisher_type')!r}; Organization|Person|unknown)")
        if not fm.get("publisher_type_source"):
            out.append(f"raw:{p.name}: publisher_type_source 누락(선언 출처 또는 none:<사유>)")
        try:
            authors = json.loads(fm.get("authors", ""))
            if not isinstance(authors, list) or any(not isinstance(a, dict) or not a.get("name") for a in authors):
                raise ValueError
        except ValueError:
            out.append(f"raw:{p.name}: authors 누락 또는 형식 오류 (JSON 배열, 없으면 [])")
        if not fm.get("authors_source"):
            out.append(f"raw:{p.name}: authors_source 누락(선언 출처 또는 none:<사유>)")
        try:
            accounts = json.loads(fm.get("accounts", ""))
            need = ("platform", "handle", "id", "role")
            if not isinstance(accounts, list) or any(not isinstance(a, dict) or any(a.get(k) in (None, "") for k in need)
                                                     or a.get("role") not in ("publisher", "author") for a in accounts):
                raise ValueError
        except ValueError:
            out.append(f"raw:{p.name}: accounts 누락 또는 형식 오류 (JSON 배열, 각 항목에 platform·handle·id·role[publisher|author]; 없으면 [])")
        if fm.get("document_type") not in ("paper", "unknown"):
            out.append(f"raw:{p.name}: document_type 누락 또는 값 오류 ({fm.get('document_type')!r}; paper|unknown)")
        if not fm.get("document_type_source"):
            out.append(f"raw:{p.name}: document_type_source 누락(선언 출처 또는 none:not-classified)")
        if not fm.get("accounts_source"):
            out.append(f"raw:{p.name}: accounts_source 누락(github-api|hf-api 또는 none:no-platform-account)")
    return out


_NOTE_BODY = re.compile(r"^> Source: [^\n]*\n\n(.*)\n$", re.S | re.M)


def _note_chunk_text(md_text: str) -> str | None:
    """collect 가 쓴 청크 노트에서 청크 본문만 꺼낸다(frontmatter·제목·Source 줄 제외)."""
    m = re.search(r"^---\n.*?\n---\n", md_text, re.S)
    rest = md_text[m.end():] if m else md_text
    b = _NOTE_BODY.search(rest)
    return b.group(1) if b else None


def orphan_md_notes(seeds: list[dict], target: Path) -> list[str]:
    """seed 가 가리키지 않는 evidence/md 노트(상대경로). seed -> md 방향의 'md_path not found' 와 반대 방향 점검이다."""
    target = Path(target).resolve()  # resolve_layout 은 resolve 된 절대경로를 돌려준다(macOS /var -> /private/var 대응)
    referenced = {str(s.get("md_path")) for s in seeds if s.get("md_path")}
    md_dir = _layout_mod.resolve_layout(target)["evidence_md_dir"]
    if not md_dir.exists():
        return []
    return sorted(str(p.relative_to(target)) for p in md_dir.rglob("*.md") if str(p.relative_to(target)) not in referenced)


def _seed_integrity_failures(seeds: list[dict], target: Path, deep: bool = True) -> list[str]:
    """seed 한 줄 단위로는 안 보이는 결함: id 중복, 본문-해시 불일치, 스냅샷 파일 부재, uri 부재."""
    import hashlib
    out: list[str] = []
    seen: dict[str, int] = {}
    for s_ in seeds:
        sid = s_.get("id", "<unknown>")
        seen[sid] = seen.get(sid, 0) + 1
    out.extend(f"{sid}: duplicate seed id ({n}x)" for sid, n in sorted(seen.items()) if n > 1)
    for s_ in seeds:
        sid = s_.get("id", "<unknown>")
        if not s_.get("uri"):
            out.append(f"{sid}: missing uri")
        if "retrieval" in s_:
            for prob in _rm.problems(s_["retrieval"], s_.get("retrieved_at")):
                out.append(f"{sid}: {prob}")
        snap = s_.get("snapshot")
        if snap and snap.get("status") == "ok":
            for k in ("pdf", "png", "html"):
                if snap.get(k) and not (target / snap[k]).exists():
                    out.append(f"{sid}: snapshot {k} not found: {snap[k]}")
        if not deep:
            continue
        md_rel = s_.get("md_path")
        ch = s_.get("content_hash") or ""
        if md_rel and (target / md_rel).is_file() and isinstance(ch, str) and ch.startswith("sha256:"):
            text = _note_chunk_text((target / md_rel).read_text(encoding="utf-8"))
            if text is None:
                out.append(f"{sid}: md note body not parseable (cannot check hash): {md_rel}")
            elif "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest() != ch:
                out.append(f"{sid}: content_hash does not match md note body: {md_rel}")
    return out


def _catalog_failures(target: Path, seeds: list[dict]) -> tuple[list[str], list[str]]:
    """카탈로그(evidence/catalog/catalog.ttl)가 있으면 SHACL·TTL↔chunks 정합을 함께 점검한다. (실패, 경고) 를 돌려준다.

    카탈로그가 없으면 아무것도 하지 않는다. rdflib/pyshacl 이 없으면 건너뛰고 경고만 남긴다(seed 검증은 그대로).
    경고: 카탈로그가 만들어진 뒤 seeds.jsonl 에 seed 가 더해지거나 빠졌다면 다시 만들어야 한다."""
    d = _layout_mod.resolve_layout(target)["catalog_dir"]
    if not (d / "catalog.ttl").is_file():
        return [], []
    try:
        import catalog_validate as _cv
        _, errors = _cv.validate_dir(d, target)
    except ImportError as exc:
        return [], [f"catalog 검증 생략({exc.name or exc} 없음) — rdflib·pyshacl 이 필요하다"]
    fails = [f"catalog: {e}" for e in errors]
    warns: list[str] = []
    chunks = d / "chunks.jsonl"
    if chunks.is_file():
        n_rows = sum(1 for _ in chunks.open("rb"))
        n_seeds = len({s_.get("id") for s_ in seeds})
        if n_rows != n_seeds:
            warns.append(f"catalog 가 seeds 와 어긋났다(청크 행 {n_rows} / seed {n_seeds}) — skb-evidence catalog --apply 로 다시 만든다")
    return fails, warns


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    target = Path(args.target).resolve()
    seeds_path = _layout_mod.resolve_layout(target)["seeds_path"]

    if not seeds_path.exists():
        print("OK: seeds.jsonl not found (0 seeds)")
        return 0

    seeds: list[dict] = []
    with seeds_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                seeds.append(obj)
            except json.JSONDecodeError as exc:
                print(f"ERROR: invalid JSON line: {exc}", file=sys.stderr)
                return 1

    if not seeds:
        print("OK: seeds.jsonl empty (0 seeds)")
        return 0

    if args.id:
        seeds = [s for s in seeds if s.get("id") == args.id]
        if not seeds:
            print(f"ERROR: seed {args.id} not found", file=sys.stderr)
            return 1

    failures: list[str] = []
    hash_re = re.compile(r'^sha256:[0-9a-f]{64}$')

    for seed in seeds:
        sid = seed.get("id", "<unknown>")

        # Check content_hash format
        ch = seed.get("content_hash") or ""      # 수동 작성 seed 는 content_hash 가 없거나 문자열이 아닐 수 있다
        if not isinstance(ch, str) or not hash_re.match(ch):
            failures.append(f"{sid}: invalid content_hash: {ch!r}")

        # Check md_path exists
        md_rel = seed.get("md_path", "")
        if md_rel:
            md_abs = target / md_rel
            if not md_abs.exists():
                failures.append(f"{sid}: md_path not found: {md_rel}")
        else:
            failures.append(f"{sid}: missing md_path field")

    failures.extend(_seed_integrity_failures(seeds, target, deep=not args.shallow))

    # --- 원문(evidence/raw) 수집일·발행일 표기 (v1.1.4, 반드시 표기)
    if not args.id:
        failures.extend(_raw_date_failures(_layout_mod.resolve_layout(target)["raw_dir"]))

    # --- seed 가 가리키지 않는 md 노트 (opt-in)
    if args.orphans and not args.id:
        orphans = orphan_md_notes(seeds, target)
        if orphans:
            shown = orphans[:20]
            msg = f"{len(orphans)} md note(s) not referenced by seeds.jsonl" + (f" (first {len(shown)}: {', '.join(shown)})" if len(orphans) > len(shown) else f": {', '.join(shown)}")
            if args.strict:
                failures.append(msg)
            else:
                print(f"WARN: {msg}", file=sys.stderr)

    # --- 카탈로그(있을 때만): SHACL·정합. seeds 와 어긋나면 경고
    if not args.id and not args.no_catalog:
        cfails, cwarns = _catalog_failures(target, seeds)
        failures.extend(cfails)
        for w in cwarns:
            print(f"WARN: {w}", file=sys.stderr)

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        print(f"\n{len(failures)} verification failure(s) in {len(seeds)} seed(s)", file=sys.stderr)
        return 1

    print(f"OK: {len(seeds)} seed(s) verified")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
