#!/usr/bin/env python3
"""Oracle: evidence_seed_readiness.

Score ∈ [0,1] based on 4 checks:
  1. URI diversity: unique URIs / total seeds (0 if no seeds)
  2. Average chunk length within [300, chunk_size] range
  3. All seeds have content_hash with sha256: prefix
  4. MD files exist for all seeds (count / total)

Can be invoked standalone:
  python3 evidence_seed_readiness.py --target REPO [--chunk-size 1200] [--run-id RUN_ID]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

HASH_RE = re.compile(r'^sha256:[0-9a-f]{64}$')
TOOL_VERSION = "skb-evidence/1.0.0"
DEFAULT_CHUNK_SIZE = 1200


def evaluate(target: Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> dict:
    """Return score dict with breakdown."""
    seeds_path = target / "evidence" / "seeds.jsonl"

    if not seeds_path.exists():
        return {
            "score": 0.0,
            "gate": "fail",
            "breakdown": {
                "uri_diversity": 0.0,
                "avg_chunk_length_ok": 0.0,
                "all_hashes_present": 0.0,
                "md_files_exist": 0.0,
            },
            "seed_count": 0,
        }

    seeds: list[dict] = []
    with seeds_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                seeds.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if not seeds:
        return {
            "score": 0.0,
            "gate": "fail",
            "breakdown": {
                "uri_diversity": 0.0,
                "avg_chunk_length_ok": 0.0,
                "all_hashes_present": 0.0,
                "md_files_exist": 0.0,
            },
            "seed_count": 0,
        }

    total = len(seeds)

    # 1. URI diversity
    unique_uris = len({s.get("uri", "") for s in seeds})
    uri_diversity = unique_uris / total

    # 2. Average chunk length check
    chunk_lengths: list[int] = []
    for s in seeds:
        chunk = s.get("chunk", {})
        preview = chunk.get("text_preview", "")
        # Use char_end - char_start as proxy for chunk length
        char_end = chunk.get("char_end", len(preview))
        char_start = chunk.get("char_start", 0)
        length = char_end - char_start if char_end > char_start else len(preview)
        chunk_lengths.append(length)

    if chunk_lengths:
        avg_len = sum(chunk_lengths) / len(chunk_lengths)
        avg_chunk_ok = 1.0 if 300 <= avg_len <= chunk_size else 0.0
    else:
        avg_chunk_ok = 0.0

    # 3. All seeds have valid content_hash
    all_hashes = all(HASH_RE.match(s.get("content_hash", "")) for s in seeds)
    all_hashes_score = 1.0 if all_hashes else 0.0

    # 4. MD files exist
    md_exists_count = 0
    for s in seeds:
        md_rel = s.get("md_path", "")
        if md_rel and (target / md_rel).exists():
            md_exists_count += 1
    md_files_score = md_exists_count / total

    breakdown = {
        "uri_diversity": round(uri_diversity, 3),
        "avg_chunk_length_ok": avg_chunk_ok,
        "all_hashes_present": all_hashes_score,
        "md_files_exist": round(md_files_score, 3),
    }

    score = sum(breakdown.values()) / 4.0
    gate = "pass" if score >= 0.85 else "warn" if score >= 0.70 else "fail"

    return {
        "score": round(score, 3),
        "gate": gate,
        "breakdown": breakdown,
        "seed_count": total,
    }


def _emit_trajectory(target: Path, run_id: str, result: dict) -> None:
    traj_dir = target / "harness" / "trajectory"
    traj_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    event = {
        "run_id": run_id,
        "ts": ts,
        "event_type": "oracle_evaluation",
        "oracle": "evidence_seed_readiness",
        "score": result["score"],
        "gate": result["gate"],
        "breakdown": result["breakdown"],
        "seed_count": result["seed_count"],
    }
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    path = traj_dir / f"run-{run_id}.jsonl"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="evidence_seed_readiness")
    p.add_argument("--target", required=True)
    p.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    p.add_argument("--run-id", default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    target = Path(args.target).resolve()
    result = evaluate(target, chunk_size=args.chunk_size)

    run_id = args.run_id
    if run_id:
        _emit_trajectory(target, run_id, result)

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")

    gate = result["gate"]
    return 0 if gate == "pass" else 1 if gate == "warn" else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
