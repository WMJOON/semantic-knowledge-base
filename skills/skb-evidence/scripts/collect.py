#!/usr/bin/env python3
"""Main collect pipeline for skb-evidence.

Flow: fetch → extract → strip-frontmatter → chunk → dedup → write seed + md note.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import chunker as _chunker  # noqa: E402
import extractor as _extractor  # noqa: E402
import fetcher as _fetcher  # noqa: E402
import layout as _layout_mod  # noqa: E402

TOOL_VERSION = "skb-evidence/1.1.2"
GENERATED_COMMENT = '<!-- msm:generated:file skill="skb-evidence" version="1.1.2" -->'

_BINARY_DOC_HINT = (
    "{kind} content detected — collect 는 바이너리 문서를 지원하지 않음"
    "(UTF-8 강제 디코딩 시 깨진 텍스트가 조용히 seed 로 등록됨). "
    "`skb-evidence ingest --source <uri>` (docling 변환) 사용."
)


def _detect_binary_doc(content_type: str, raw: bytes, uri: str = "") -> str | None:
    """PDF/오피스 바이너리를 감지해 kind 라벨을 반환. 텍스트/HTML 이면 None."""
    ct = content_type.lower()
    head = raw[:8]
    if "pdf" in ct or head.startswith(b"%PDF-"):
        return "PDF"
    if head.startswith(b"PK\x03\x04") and (
        "officedocument" in ct or "opendocument" in ct
        or re.search(r"\.(docx|xlsx|pptx|odt)(\?|#|$)", uri.lower())
    ):
        return "Office(zip)"
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "Office(legacy binary)"
    return None


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def _slug_from_uri(uri: str) -> str:
    """Derive deterministic slug from URI (max 40 chars, unique per URI).

    Non-ASCII path segments (한글 법령명 등) collapse to a single '_' under the
    alnum-only filter below, so two URIs differing only in a Korean segment
    (예: kr/소득세법/시행령.md vs kr/지방세법/시행령.md) produced the SAME slug —
    later ingests silently overwrote earlier ones' evidence/md/*.md files and
    created duplicate-id records in seeds.jsonl (실제 사고: 2026-08-29, 소득세법
    시행령 수집이 이미 등록된 524개 청크를 덮어씀). A short hash of the full URI
    is appended so any two distinct URIs always get distinct slugs, even when
    their ASCII-only content collapses identically.
    """
    import urllib.parse
    lower = uri.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        parsed = urllib.parse.urlparse(uri)
        base = parsed.hostname or ""
        path = parsed.path.strip("/").replace("/", "_")
        raw = (base + "_" + path).lower()
    elif lower.startswith("file://"):
        parsed = urllib.parse.urlparse(uri)
        p = Path(parsed.path)
        raw = p.stem.lower()
    else:
        p = Path(uri)
        raw = p.stem.lower()
    # Keep only alnum and underscore
    slug = re.sub(r'[^a-z0-9]+', '_', raw)
    slug = slug.strip('_')
    uri_hash = hashlib.sha256(uri.encode("utf-8")).hexdigest()[:8]
    return (slug[:31] or "source") + "_" + uri_hash


# ---------------------------------------------------------------------------
# Frontmatter stripper
# ---------------------------------------------------------------------------

def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter block (--- ... ---) from start of text."""
    m = re.match(r'^---\s*\n.*?\n---\s*\n', text, re.DOTALL)
    if m:
        return text[m.end():]
    return text


def _frontmatter_source(text: str) -> str | None:
    """local file 이 convert.py 등으로 생성된 중간 산출물일 때, frontmatter의
    'source: <원본 URL>'을 읽어 원본 provenance 를 복원한다.

    local 파일 경로를 그대로 --source로 넘기면 uri 필드가 로컬 경로가 되어
    원본 웹 출처가 유실된다(consumer KB TS-0008/TS-0010에서 재현 확인).
    """
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if not m:
        return None
    fm_match = re.search(r'^source:\s*(\S+)\s*$', m.group(1), re.MULTILINE)
    return fm_match.group(1) if fm_match else None


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Seeds JSONL I/O
# ---------------------------------------------------------------------------

def _load_existing_hashes(seeds_path: Path) -> set[str]:
    """Return set of content_hash strings already in seeds.jsonl."""
    hashes: set[str] = set()
    if not seeds_path.exists():
        return hashes
    with seeds_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                h = obj.get("content_hash", "")
                if h:
                    hashes.add(h)
            except json.JSONDecodeError:
                pass
    return hashes


def _append_seed(seeds_path: Path, seed: dict) -> None:
    """Atomic-append a single seed JSON line to seeds.jsonl."""
    line = json.dumps(seed, ensure_ascii=False, separators=(",", ":")) + "\n"
    seeds_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(seeds_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# MD note writer
# ---------------------------------------------------------------------------

def _write_md_note(md_dir: Path, slug: str, idx: int, seed: dict, chunk_text: str) -> None:
    """Write evidence/md/<slug>_<pad4>.md for a single chunk."""
    filename = f"{slug}_{idx:04d}.md"
    out_path = md_dir / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)

    title = seed.get("title") or slug
    uri = seed.get("uri", "")
    retrieved = seed.get("retrieved_at", "")
    content_hash = seed.get("content_hash", "")
    chunk_total = seed["chunk"]["total"]

    content = (
        f"{GENERATED_COMMENT}\n"
        f"---\n"
        f"id: {seed['id']}\n"
        f"uri: {uri}\n"
        f"retrieved_at: {retrieved}\n"
        f"content_hash: {content_hash}\n"
        f"chunk_index: {idx}\n"
        f"chunk_total: {chunk_total}\n"
        f"status: collected\n"
        f"---\n"
        f"\n"
        f"# {title}\n"
        f"\n"
        f"> Source: {uri}\n"
        f"\n"
        f"{chunk_text}\n"
    )
    out_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Trajectory writer
# ---------------------------------------------------------------------------

def _emit_trajectory(target: Path, run_id: str | None, event: dict) -> None:
    if not run_id:
        return
    traj_dir = target / "harness" / "trajectory"
    traj_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    record = {"run_id": run_id, "ts": ts, **event}
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    path = traj_dir / f"run-{run_id}.jsonl"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Core collect logic
# ---------------------------------------------------------------------------

def collect_uri(
    uri: str,
    target: Path,
    chunk_size: int,
    chunk_overlap: int,
    cluster: str | None,
    apply: bool,
    run_id: str | None,
    user_agent: str,
    max_retry: int,
    capture: bool = False,
) -> dict:
    """Collect a single URI. Returns stats dict."""
    stats = {"uri": uri, "added": 0, "skipped": 0, "error": None}

    # Fetch
    try:
        kind, raw, content_type, effective_uri = _fetcher.fetch(
            uri, user_agent=user_agent, max_retry=max_retry
        )
    except Exception as exc:
        stats["error"] = str(exc)
        return stats

    # local 파일(kind != "url")이 convert.py 등이 생성한 중간 산출물이면
    # frontmatter의 원본 source URL로 uri를 복원한다. 원격 fetch 콘텐츠는
    # 신뢰하지 않는다(임의 웹페이지가 provenance를 위조하는 경로 차단).
    if kind != "url":
        fm_source = _frontmatter_source(raw.decode("utf-8", errors="replace"))
        if fm_source:
            uri = fm_source
            stats["uri"] = uri

    slug = _slug_from_uri(uri)
    retrieved_at = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    binary_kind = _detect_binary_doc(content_type, raw, uri)
    if binary_kind is not None:
        stats["error"] = _BINARY_DOC_HINT.format(kind=binary_kind)
        return stats

    # Extract text
    if "html" in content_type.lower() or raw[:200].lstrip()[:5].lower() in (b"<!doc", b"<html"):
        title, text = _extractor.extract_html(raw)
    else:
        title_raw = ""
        text = raw.decode("utf-8", errors="replace")
        # Strip frontmatter for MD files
        text = _strip_frontmatter(text)
        title_raw = slug

    if "html" in content_type.lower() or raw[:200].lstrip()[:5].lower() in (b"<!doc", b"<html"):
        pass  # title already set above
    else:
        title = title_raw

    if not text.strip():
        stats["error"] = "empty content after extraction"
        return stats

    # Chunk
    chunks = _chunker.chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        stats["error"] = "no chunks produced"
        return stats

    total = len(chunks)

    if not apply:
        # Dry run: just report what would be added
        stats["added"] = total
        stats["dry_run"] = True
        return stats

    # Load existing hashes for dedup
    _layout = _layout_mod.resolve_layout(target)
    seeds_path = _layout["seeds_path"]
    md_dir = _layout["evidence_md_dir"]
    existing_hashes = _load_existing_hashes(seeds_path)

    # Source snapshot capture (opt-in, URL당 1회 — chunk 루프 이전).
    # 캡처 실패는 수집을 막지 않음(graceful degrade): snapshot.status="error" 기록 후 계속.
    snapshot = None
    if capture and kind == "url":
        # lazy: capture 모듈은 이 분기에서만 import → 비캡처 경로 playwright 무관 (AC-6)
        import capture as _capture  # noqa: E402
        rec = _capture.capture_to_target(uri, target)
        snapshot = {
            "pdf": rec.get("pdf"),
            "png": rec.get("png"),
            "html": rec.get("html"),
            "captured_at": rec.get("captured_at"),
            "status": rec.get("status", "error"),
        }
        if rec.get("status") != "ok":
            snapshot["error"] = rec.get("error")
        _emit_trajectory(target, run_id, {
            "event_type": "source_captured",
            "uri": uri,
            "sha": rec.get("sha"),
            "status": rec.get("status"),
        })

    for idx, chunk_text in enumerate(chunks):
        content_hash = _sha256(chunk_text)
        if content_hash in existing_hashes:
            stats["skipped"] += 1
            _emit_trajectory(target, run_id, {
                "event_type": "seed_dedup_skip",
                "content_hash": content_hash,
                "uri": uri,
                "chunk_index": idx,
            })
            continue

        seed_id = f"evidence:seed:{slug}_{idx:04d}"
        md_rel = _layout_mod.rel(target, md_dir / f"{slug}_{idx:04d}.md")
        seed = {
            "id": seed_id,
            "kind": kind,
            "uri": uri,
            "retrieved_at": retrieved_at,
            "content_hash": content_hash,
            "title": title or slug,
            "chunk": {
                "index": idx,
                "total": total,
                "char_start": 0,  # approximate (overlap makes exact start ambiguous)
                "char_end": len(chunk_text),
                "text_preview": chunk_text[:200],
            },
            "claims": [],
            "status": "collected",
            "cluster_hint": cluster,
            "md_path": md_rel,
            "tool_version": TOOL_VERSION,
        }
        # 같은 URI 의 모든 chunk-seed 가 동일 snapshot 참조 (URL당 1회 캡처)
        if snapshot is not None:
            seed["snapshot"] = snapshot

        # Write md note
        _write_md_note(md_dir, slug, idx, seed, chunk_text)

        # Append seed
        _append_seed(seeds_path, seed)
        existing_hashes.add(content_hash)
        stats["added"] += 1

        _emit_trajectory(target, run_id, {
            "event_type": "seed_collected",
            "seed_id": seed_id,
            "content_hash": content_hash,
            "chunk_index": idx,
            "chunk_total": total,
        })

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="collect")
    p.add_argument("--target", default=".", help="KB root path")
    p.add_argument("--source", nargs="+", default=[], metavar="URI")
    p.add_argument("--sources-file", default=None, metavar="PATH")
    p.add_argument("--chunk-size", type=int, default=1200)
    p.add_argument("--chunk-overlap", type=int, default=100)
    p.add_argument("--cluster", default=None)
    p.add_argument("--dry-run", action="store_true", default=False)
    p.add_argument("--apply", action="store_true", default=False)
    p.add_argument("--max-retry", type=int, default=1)
    p.add_argument("--user-agent", default="skb-evidence/1.0")
    p.add_argument("--run-id", default=None)
    p.add_argument("--capture", action="store_true", default=False,
                   help="URL 소스 원문 스냅샷(PDF/PNG/HTML) 캡처 후 seed.snapshot 기록 "
                        "(opt-in; requires: pip install playwright && playwright install chromium)")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    target = Path(args.target).resolve()

    # Gather URIs
    uris: list[str] = list(args.source)
    if args.sources_file:
        sf = Path(args.sources_file)
        if sf.exists():
            for line in sf.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    uris.append(line)

    if not uris:
        print("No sources specified.", file=sys.stderr)
        return 2

    apply = args.apply and not args.dry_run

    all_stats: list[dict] = []
    for uri in uris:
        stats = collect_uri(
            uri=uri,
            target=target,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            cluster=args.cluster,
            apply=apply,
            run_id=args.run_id,
            user_agent=args.user_agent,
            max_retry=args.max_retry,
            capture=args.capture,
        )
        all_stats.append(stats)
        if stats.get("error"):
            print(f"ERROR: {uri}: {stats['error']}", file=sys.stderr)
        else:
            mode = "dry-run" if not apply else "applied"
            print(f"[{mode}] {uri}: added={stats['added']} skipped={stats['skipped']}")

    total_added = sum(s["added"] for s in all_stats)
    total_skipped = sum(s["skipped"] for s in all_stats)
    errors = [s for s in all_stats if s.get("error")]
    print(f"\nSummary: added={total_added} skipped={total_skipped} errors={len(errors)}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
