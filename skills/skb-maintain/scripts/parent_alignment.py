#!/usr/bin/env python3
"""skb-maintain parent_alignment — scan parent-node alignment.

v0.11.0 신규 스킬. 6가지 검증 규칙 (Rule 1~5 + Rule 3-bis 단일부모)을 read-only로 적용.

Usage:
  python3 parent_alignment.py --target REPO [--root projection/wikigraph/class]
                              [--output PATH] [--format json|markdown]
                              [--accept-hub-suffix]

Rules:
  R1  parent_existence       — 디렉토리에 {name}__class.md (또는 __hub.md 후방호환) 필수
  R2  naming_consistency     — 부모 노드 파일명 = 디렉토리명
  R3  belongs_to_missing     — 자식 frontmatter에 belongs_to 명시
  R3b multiple_parents       — 자식은 belongs_to 1개만 (D-2)
  R4  self_reference         — 부모가 자기 자신을 belongs_to 안 함
  R5  bidirectional          — 부모 본문에 자식 인덱싱

Special:
  - unclassified/ 디렉토리는 R1 면제
  - L0~L4 권장, L5+ 경고
  - read-only (vault 변경 없음)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

TOOL_VERSION = "skb-maintain/1.1.0-scan"

# --------------------------------------------------------------------------
# Frontmatter parser (stdlib-only)
# --------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(path: Path) -> dict[str, Any]:
    """Parse YAML frontmatter without PyYAML.

    Handles enough of the format for our needs:
      - scalar key: value
      - list key:\n  - value\n  - value
      - nested dict (limited; relations list of dicts)
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return {}
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    return _parse_yaml_block(m.group(1))


def _parse_yaml_block(block: str) -> dict[str, Any]:
    lines = block.splitlines()
    result: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if not line.startswith(" "):  # top-level key
            if ":" not in line:
                i += 1
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "" or val is None:
                # Maybe block-list or block-dict follows
                children: list[Any] = []
                j = i + 1
                while j < len(lines) and (
                    lines[j].startswith("  ") or lines[j].startswith("\t") or lines[j].strip() == ""
                ):
                    sub = lines[j]
                    if sub.lstrip().startswith("- "):
                        item_line = sub.lstrip()[2:]
                        if ":" in item_line:
                            sub_dict: dict[str, str] = {}
                            sk, _, sv = item_line.partition(":")
                            sub_dict[sk.strip()] = _strip_quote(sv.strip())
                            k = j + 1
                            while k < len(lines) and lines[k].startswith("    "):
                                inner = lines[k].lstrip()
                                if ":" in inner:
                                    ik, _, iv = inner.partition(":")
                                    sub_dict[ik.strip()] = _strip_quote(iv.strip())
                                k += 1
                            children.append(sub_dict)
                            j = k
                            continue
                        else:
                            children.append(_strip_quote(item_line))
                    j += 1
                result[key] = children
                i = j
                continue
            result[key] = _strip_quote(val)
            i += 1
        else:
            i += 1
    return result


def _strip_quote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

UNCLASSIFIED_DIRS = {"unclassified"}
PARENT_SUFFIX_CLASS = "__class.md"
PARENT_SUFFIX_HUB = "__hub.md"  # 후방호환

ENTITY_PATTERN = re.compile(r"^(concept|pattern|antipattern|technique|framework|oracle|template|instance|process|figure|method|policy|task|skill|tool|model|metric|use_case|asset)__.*\.md$")


def is_entity_file(path: Path) -> bool:
    # 부모 노드(__class.md, __hub.md)는 entity로 취급 안 함
    if path.name.endswith(PARENT_SUFFIX_CLASS) or path.name.endswith(PARENT_SUFFIX_HUB):
        return False
    return bool(ENTITY_PATTERN.match(path.name))


def is_parent_file(path: Path) -> bool:
    return path.name.endswith(PARENT_SUFFIX_CLASS) or path.name.endswith(PARENT_SUFFIX_HUB)


def parent_basename(directory: Path, suffix: str) -> str:
    return f"{directory.name}{suffix}"


def is_unclassified(directory: Path) -> bool:
    return directory.name in UNCLASSIFIED_DIRS


# --------------------------------------------------------------------------
# Violations
# --------------------------------------------------------------------------

@dataclass
class Violation:
    rule: str
    severity: str  # "error" | "warning" | "info"
    directory: str | None = None
    file: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    suggested: str | None = None


@dataclass
class ScanReport:
    version: str = TOOL_VERSION
    scanned_at: str = ""
    target: str = ""
    root: str = ""
    accept_hub_suffix: bool = True

    violations: list[Violation] = field(default_factory=list)

    summary: dict[str, int] = field(default_factory=dict)
    unclassified_summary: dict[str, int] = field(default_factory=dict)
    level_summary: dict[str, int] = field(default_factory=dict)
    naming_summary: dict[str, int] = field(default_factory=dict)

    def add(self, v: Violation) -> None:
        self.violations.append(v)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["violations"] = [asdict(v) for v in self.violations]
        return d


# --------------------------------------------------------------------------
# Rule validators
# --------------------------------------------------------------------------

def rule_parent_existence(directory: Path, accept_hub: bool) -> Violation | None:
    if is_unclassified(directory):
        return None
    entity_files = [p for p in directory.iterdir() if p.is_file() and is_entity_file(p)]
    if not entity_files:
        return None
    class_file = directory / parent_basename(directory, PARENT_SUFFIX_CLASS)
    hub_file = directory / parent_basename(directory, PARENT_SUFFIX_HUB)
    if class_file.exists():
        return None
    if accept_hub and hub_file.exists():
        return Violation(
            rule="parent_existence",
            severity="warning",
            directory=str(directory),
            detail={"found": hub_file.name, "expected": class_file.name},
            suggested=f"rename {hub_file.name} -> {class_file.name}",
        )
    return Violation(
        rule="parent_existence",
        severity="error",
        directory=str(directory),
        detail={"expected": class_file.name, "entity_count": len(entity_files)},
        suggested=f"create_parent {directory}/{class_file.name}",
    )


def rule_naming_consistency(directory: Path, accept_hub: bool) -> list[Violation]:
    """디렉토리 내 __class.md 또는 __hub.md 파일의 명명 일관성."""
    if is_unclassified(directory):
        return []
    out: list[Violation] = []
    expected_class = parent_basename(directory, PARENT_SUFFIX_CLASS)
    expected_hub = parent_basename(directory, PARENT_SUFFIX_HUB)
    for p in directory.iterdir():
        if not p.is_file():
            continue
        if p.name.endswith(PARENT_SUFFIX_CLASS):
            if p.name != expected_class:
                out.append(Violation(
                    rule="naming_consistency",
                    severity="error",
                    file=str(p),
                    detail={"found": p.name, "expected": expected_class},
                    suggested=f"rename {p.name} -> {expected_class}",
                ))
        elif p.name.endswith(PARENT_SUFFIX_HUB):
            if accept_hub and p.name != expected_hub:
                out.append(Violation(
                    rule="naming_consistency",
                    severity="error",
                    file=str(p),
                    detail={"found": p.name, "expected_hub": expected_hub, "expected_class": expected_class},
                    suggested=f"rename {p.name} -> {expected_class}",
                ))
    return out


def rule_belongs_to(child: Path, parent_dir: Path) -> list[Violation]:
    """R3 + R3-bis: belongs_to 명시 + 단일 부모."""
    out: list[Violation] = []
    fm = parse_frontmatter(child)
    relations = fm.get("relations", [])
    if not isinstance(relations, list):
        relations = []

    belongs_to = [r for r in relations if isinstance(r, dict) and r.get("type") == "belongs_to"]

    expected_class = parent_basename(parent_dir, PARENT_SUFFIX_CLASS).removesuffix(".md")
    expected_hub = parent_basename(parent_dir, PARENT_SUFFIX_HUB).removesuffix(".md")

    if not belongs_to:
        out.append(Violation(
            rule="belongs_to_missing",
            severity="error",
            file=str(child),
            detail={"expected_parent": expected_class},
            suggested=f"add_relation belongs_to -> [[{expected_class}|...]]",
        ))
    else:
        # 단일 부모 (R3-bis)
        if len(belongs_to) > 1:
            out.append(Violation(
                rule="multiple_parents",
                severity="error",
                file=str(child),
                detail={"count": len(belongs_to), "targets": [r.get("target", "") for r in belongs_to]},
                suggested="demote_to_cross_reference",
            ))
        # 부모 ID가 디렉토리와 일치하는지
        primary = belongs_to[0]
        target = primary.get("target", "")
        if expected_class not in target and expected_hub not in target:
            out.append(Violation(
                rule="belongs_to_mismatch",
                severity="warning",
                file=str(child),
                detail={"declared": target, "expected": expected_class},
                suggested=f"verify_parent target should reference [[{expected_class}|...]]",
            ))

    return out


_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\||\]\])")


def _extract_wikilink_id(target: str) -> str:
    m = _WIKILINK_RE.search(target)
    return m.group(1).strip() if m else ""


def rule_self_reference(parent_file: Path) -> Violation | None:
    fm = parse_frontmatter(parent_file)
    declared_id = fm.get("entity") or fm.get("entity_id") or parent_file.stem
    # 부모 노드의 실제 stem (예: pattern__class)이 우선
    stem_id = parent_file.stem
    relations = fm.get("relations", [])
    if not isinstance(relations, list):
        return None
    for r in relations:
        if not isinstance(r, dict):
            continue
        if r.get("type") != "belongs_to":
            continue
        target_id = _extract_wikilink_id(r.get("target", ""))
        if target_id and (target_id == declared_id or target_id == stem_id):
            return Violation(
                rule="self_reference",
                severity="error",
                file=str(parent_file),
                detail={"entity_id": declared_id, "stem": stem_id, "target_id": target_id},
                suggested="remove_self_belongs_to",
            )
    return None


def rule_bidirectional(parent_file: Path, directory: Path) -> list[Violation]:
    """부모 본문에 자식 인덱스가 있는지 (간단 휴리스틱)."""
    try:
        body = parent_file.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    missing: list[str] = []
    for child in directory.iterdir():
        if not child.is_file() or not is_entity_file(child):
            continue
        child_id = child.stem
        # wikilink 또는 인라인 텍스트로 참조되는지
        if child_id not in body:
            missing.append(child.name)

    if missing:
        return [Violation(
            rule="parent_index_missing",
            severity="warning",
            file=str(parent_file),
            detail={"missing_children": missing[:10], "missing_count": len(missing)},
            suggested="update_parent_index",
        )]
    return []


def rule_level_check(parent_file: Path, root: Path) -> Violation | None:
    fm = parse_frontmatter(parent_file)
    declared = fm.get("level")
    try:
        rel = parent_file.parent.relative_to(root)
    except ValueError:
        return None
    depth = len(rel.parts)
    inferred = f"L{depth}"

    if depth >= 5:
        return Violation(
            rule="deep_nesting",
            severity="warning",
            file=str(parent_file),
            detail={"level": inferred, "depth": depth},
            suggested="L4 이하 권장",
        )
    if declared and declared != inferred:
        return Violation(
            rule="level_mismatch",
            severity="warning",
            file=str(parent_file),
            detail={"declared": declared, "inferred": inferred},
            suggested=f"update level to {inferred}",
        )
    return None


# --------------------------------------------------------------------------
# Scanner
# --------------------------------------------------------------------------

def walk_entity_directories(root: Path):
    """root 아래의 모든 디렉토리를 yield. entity 파일이 하나라도 있어야 함."""
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            yield p


def scan(target: Path, root_rel: str, accept_hub: bool) -> ScanReport:
    import datetime
    report = ScanReport()
    report.scanned_at = datetime.datetime.utcnow().isoformat() + "Z"
    report.target = str(target)
    report.root = root_rel
    report.accept_hub_suffix = accept_hub

    root = (target / root_rel).resolve()
    if not root.exists():
        print(f"❌ root not found: {root}", file=sys.stderr)
        return report

    dirs_scanned = 0

    for directory in walk_entity_directories(root):
        # Skip if directory has no entity files
        try:
            children = list(directory.iterdir())
        except PermissionError:
            continue
        entity_files = [p for p in children if p.is_file() and is_entity_file(p)]

        # unclassified/ 디렉토리에서 self-summary 카운트
        if is_unclassified(directory):
            for p in entity_files:
                key = str(p.relative_to(target))
                report.unclassified_summary[key] = 0
            continue

        # parent_file 후보
        class_path = directory / parent_basename(directory, PARENT_SUFFIX_CLASS)
        hub_path = directory / parent_basename(directory, PARENT_SUFFIX_HUB)
        parent_file: Path | None = None
        if class_path.exists():
            parent_file = class_path
        elif accept_hub and hub_path.exists():
            parent_file = hub_path

        # 디렉토리 스캔 대상이 entity 또는 parent_file 있는 경우만
        if not entity_files and parent_file is None:
            continue

        dirs_scanned += 1

        # R1
        v = rule_parent_existence(directory, accept_hub)
        if v:
            report.add(v)

        # R2
        for v in rule_naming_consistency(directory, accept_hub):
            report.add(v)

        # R3, R3-bis
        for child in entity_files:
            for v in rule_belongs_to(child, directory):
                report.add(v)

        # R4, R5, level
        if parent_file:
            v = rule_self_reference(parent_file)
            if v:
                report.add(v)
            for v in rule_bidirectional(parent_file, directory):
                report.add(v)
            v = rule_level_check(parent_file, root)
            if v:
                report.add(v)

            # 명명 통계
            if parent_file.name.endswith(PARENT_SUFFIX_CLASS):
                report.naming_summary["class"] = report.naming_summary.get("class", 0) + 1
            else:
                report.naming_summary["hub"] = report.naming_summary.get("hub", 0) + 1

    # 요약
    rule_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
    for v in report.violations:
        rule_counts[v.rule] = rule_counts.get(v.rule, 0) + 1
        severity_counts[v.severity] = severity_counts.get(v.severity, 0) + 1
    report.summary = {
        "directories_scanned": dirs_scanned,
        "violations_total": len(report.violations),
        **{f"rule_{k}": v for k, v in rule_counts.items()},
        **{f"severity_{k}": v for k, v in severity_counts.items()},
    }

    # unclassified entity 카운트
    report.unclassified_summary["total_pending_review"] = len(report.unclassified_summary)

    return report


# --------------------------------------------------------------------------
# Reporters
# --------------------------------------------------------------------------

def render_markdown(report: ScanReport) -> str:
    lines = []
    lines.append(f"# Parent-Alignment Scan Report")
    lines.append("")
    lines.append(f"- **Tool**: `{report.version}`")
    lines.append(f"- **Target**: `{report.target}`")
    lines.append(f"- **Root**: `{report.root}`")
    lines.append(f"- **Scanned at**: {report.scanned_at}")
    lines.append(f"- **Accept `__hub.md` suffix**: {report.accept_hub_suffix}")
    lines.append("")

    lines.append("## 📊 Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    for k, v in report.summary.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    lines.append("## 📛 Naming")
    lines.append("")
    lines.append("| Suffix | Count |")
    lines.append("|--------|-------|")
    for k, v in report.naming_summary.items():
        lines.append(f"| `__{k}.md` | {v} |")
    lines.append("")

    # Group violations by rule
    grouped: dict[str, list[Violation]] = {}
    for v in report.violations:
        grouped.setdefault(v.rule, []).append(v)

    severity_emoji = {"error": "🔴", "warning": "🟡", "info": "🔵"}

    lines.append("## 🚨 Violations by Rule")
    lines.append("")
    for rule, items in sorted(grouped.items(), key=lambda x: -len(x[1])):
        sev = items[0].severity
        lines.append(f"### {severity_emoji.get(sev, '⚪')} `{rule}` — {len(items)}건")
        lines.append("")
        for v in items[:30]:  # cap at 30
            target = v.file or v.directory or "?"
            lines.append(f"- `{target}`")
            if v.detail:
                detail_str = ", ".join(f"{k}={v}" for k, v in v.detail.items() if k != "missing_children")
                if detail_str:
                    lines.append(f"  - {detail_str}")
            if v.suggested:
                lines.append(f"  - 💡 {v.suggested}")
        if len(items) > 30:
            lines.append(f"- _(외 {len(items) - 30}건 생략)_")
        lines.append("")

    if report.unclassified_summary:
        lines.append("## 📂 Unclassified Summary")
        lines.append("")
        for k, v in report.unclassified_summary.items():
            lines.append(f"- `{k}`: {v}")
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True, help="Vault root path")
    parser.add_argument("--root", default="projection/wikigraph/class", help="Derived projection root (relative to --target)")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--accept-hub-suffix", dest="accept_hub", action="store_true", default=True,
                        help="Treat __hub.md as parent (backward compat, default ON)")
    parser.add_argument("--no-accept-hub-suffix", dest="accept_hub", action="store_false",
                        help="Strict: only __class.md is accepted as parent")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"❌ target not found: {target}", file=sys.stderr)
        sys.exit(1)

    report = scan(target, args.root, args.accept_hub)

    if args.format == "json":
        content = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
    else:
        content = render_markdown(report)

    if args.output:
        Path(args.output).write_text(content, encoding="utf-8")
        print(f"✅ Report written to: {args.output}", file=sys.stderr)
        print(f"   - violations: {len(report.violations)}", file=sys.stderr)
    else:
        print(content)


if __name__ == "__main__":
    main()
