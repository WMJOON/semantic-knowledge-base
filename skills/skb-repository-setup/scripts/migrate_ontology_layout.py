#!/usr/bin/env python3
"""이전 배치(ontology/system/{semantic,kinetic,dynamic})를 새 배치(ontology/{semantic,kinetic,dynamic})로 옮긴다.

기본은 드라이런이다. `--apply` 를 줘야 실제로 바꾼다. 삭제는 하지 않는다.
- 디렉토리는 rename 으로 옮긴다. 목적지가 이미 있으면 충돌로 보고 아무것도 바꾸지 않는다.
- 옮긴 뒤 ontology/system 이 비어 있으면 rmdir 한다. 파일이 남아 있으면 남긴 채로 보고한다.
- canonical_root_hub.yaml 에 layout.semantic_dir 을 선언하고, 옛 경로 문자열을 새 경로로 바꾼다.
- agent-context/index/index.yaml 과 KB 메타데이터(ttl·yaml·json·jsonl·md)의 옛 경로 문자열을 바꾼다.
  evidence/ 아래 원문은 건드리지 않는다.
- 두 번 돌려도 같은 결과다(idempotent).

사용: migrate_ontology_layout.py --target KB [--apply] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

OLD = "ontology/system"
NEW = "ontology"
SUBDIRS = ("semantic", "kinetic", "dynamic")
TEXT_SUFFIXES = (".ttl", ".yaml", ".yml", ".json", ".jsonl", ".md")
SKIP_PARTS = {".git", ".venv", ".venv-py39-old", "node_modules", "__pycache__", ".pytest_cache", "evidence", "planning"}


def plan_moves(target: Path) -> tuple[list[tuple[Path, Path]], list[str]]:
    moves, conflicts = [], []
    for sub in SUBDIRS:
        src = target / "ontology" / "system" / sub
        dst = target / "ontology" / sub
        if not src.exists():
            continue
        if dst.exists() and not (dst.is_dir() and not any(dst.iterdir())):
            conflicts.append(f"{sub}: 옛 경로와 새 경로가 모두 있다 ({src.relative_to(target)}, {dst.relative_to(target)})")
        else:
            moves.append((src, dst))  # 없거나 빈 새 경로는 잃을 내용이 없다
    return moves, conflicts


def hub_edits(target: Path) -> tuple[Path | None, str | None]:
    hub = target / "canonical_root_hub.yaml"
    if not hub.exists():
        return None, None
    s = hub.read_text(encoding="utf-8")
    new = s
    if re.search(r"(?m)^layout:\s*$", new):
        if re.search(r"(?m)^  semantic_dir:\s*ontology/system/semantic\s*$", new):
            new = re.sub(r"(?m)^  semantic_dir:\s*ontology/system/semantic\s*$", "  semantic_dir: ontology/semantic", new)
        elif not re.search(r"(?m)^  semantic_dir:", new):
            new = re.sub(r"(?m)^layout:\s*$", "layout:\n  semantic_dir: ontology/semantic", new, count=1)
    else:
        new = new.rstrip("\n") + "\n\nlayout:\n  semantic_dir: ontology/semantic\n"
    new = new.replace("ontology/system/semantic/", "ontology/semantic/")
    new = new.replace("ontology/system/kinetic/", "ontology/kinetic/").replace("ontology/system/dynamic/", "ontology/dynamic/")
    return (hub, new) if new != s else (None, None)


def text_edits(target: Path) -> list[tuple[Path, int]]:
    out = []
    for p in sorted(target.rglob("*")):
        if not p.is_file() or p.suffix not in TEXT_SUFFIXES:
            continue
        rel = p.relative_to(target)
        if set(rel.parts) & SKIP_PARTS or rel.name == "canonical_root_hub.yaml":
            continue
        try:
            s = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        n = len(re.findall(r"ontology/system/(semantic|kinetic|dynamic)/", s))
        if n:
            out.append((p, n))
    return out


def rewrite_text(path: Path) -> None:
    s = path.read_text(encoding="utf-8")
    s = re.sub(r"ontology/system/(semantic|kinetic|dynamic)/", r"ontology/\1/", s)
    path.write_text(s, encoding="utf-8")


def leftover_system(target: Path, moving: tuple[Path, ...] = ()) -> list[str]:
    system = target / "ontology" / "system"
    if not system.exists():
        return []
    return sorted(str(p.relative_to(target)) for p in system.rglob("*")
                  if p.is_file() and not any(p.is_relative_to(m) for m in moving))


def run(target: Path, apply: bool) -> dict:
    report: dict = {"target": str(target), "apply": apply, "moves": [], "conflicts": [], "hub": None,
                    "text_files": [], "removed_empty": [], "leftover": []}
    if not (target / "ontology").exists():
        report["conflicts"].append("ontology/ 가 없다. 이전 배치 KB 가 아니다")
        return report
    moves, conflicts = plan_moves(target)
    report["conflicts"] = conflicts
    report["moves"] = [f"{s.relative_to(target)} -> {d.relative_to(target)}" for s, d in moves]
    hub, new_hub = hub_edits(target)
    report["hub"] = str(hub.relative_to(target)) if hub else None
    texts = text_edits(target)
    report["text_files"] = [f"{p.relative_to(target)} ({n})" for p, n in texts]
    if conflicts:
        return report  # 충돌이 있으면 아무것도 바꾸지 않는다
    if not apply:
        report["leftover"] = leftover_system(target, tuple(s for s, _ in moves))
        return report
    # 텍스트 치환은 옮기기 전 경로로 한다. 옮긴 뒤에는 목록의 경로가 바뀌어 있다.
    for p, _ in texts:
        rewrite_text(p)
    if hub and new_hub is not None:
        hub.write_text(new_hub, encoding="utf-8")
    for src, dst in moves:
        if dst.exists():
            dst.rmdir()  # 빈 디렉토리만 여기까지 온다 (plan_moves 가 막는다)
        src.rename(dst)
    system = target / "ontology" / "system"
    if system.exists():
        for d in sorted(system.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        if system.exists() and not any(system.iterdir()):
            system.rmdir()
            report["removed_empty"].append("ontology/system")
    report["leftover"] = leftover_system(target)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", required=True)
    ap.add_argument("--apply", action="store_true", help="실제로 바꾼다 (기본은 드라이런)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rep = run(Path(a.target).resolve(), a.apply)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        mode = "적용" if a.apply else "드라이런 (--apply 로 적용)"
        print(f"[migrate-ontology-layout] {mode}: {rep['target']}")
        for m in rep["moves"]:
            print(f"  이동  {m}")
        if rep["hub"]:
            print(f"  허브  {rep['hub']} (layout.semantic_dir 선언, 옛 경로 치환)")
        for t in rep["text_files"]:
            print(f"  치환  {t}")
        for c in rep["conflicts"]:
            print(f"  충돌  {c}")
        if rep["conflicts"]:
            print("  충돌이 있어 아무것도 바꾸지 않았다. 해결한 뒤 다시 실행한다.")
        for left in rep["leftover"]:
            print(f"  남음  {left} (자동으로 지우지 않는다)")
    return 1 if rep["conflicts"] else 0


if __name__ == "__main__":
    sys.exit(main())
