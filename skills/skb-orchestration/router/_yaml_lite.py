"""Minimal YAML subset reader.

We avoid a hard pyyaml dependency. Only supports the subset of YAML actually
used by skb-orchestration reference files:
  - mappings (key: value, key:\\n  nested)
  - sequences (- value, - key: value [nested])
  - scalars: strings (with or without quotes), int, float, bool, null
  - end-of-line comments via leading `# `
No anchors, no flow style, no folded blocks, no multi-document.
"""

from __future__ import annotations

from typing import Any


def _scalar(raw: str) -> Any:
    v = raw.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    if v.startswith("[") and v.endswith("]"):
        # flow sequence: ["a", "b", 3]
        inner = v[1:-1].strip()
        if not inner:
            return []
        # simple comma split (no nested flow support)
        return [_scalar(part) for part in _split_flow(inner)]
    if v.startswith("{") and v.endswith("}"):
        return {}  # flow mapping unsupported; placeholder
    if v == "null" or v == "~" or v == "":
        return None
    if v == "true":
        return True
    if v == "false":
        return False
    try:
        if "." in v or "e" in v or "E" in v:
            return float(v)
        return int(v)
    except ValueError:
        return v


def _split_flow(s: str) -> list[str]:
    """Comma-split that respects simple quoted strings."""
    parts: list[str] = []
    buf = ""
    quote = ""
    for ch in s:
        if quote:
            buf += ch
            if ch == quote:
                quote = ""
            continue
        if ch in ('"', "'"):
            quote = ch
            buf += ch
            continue
        if ch == ",":
            parts.append(buf)
            buf = ""
            continue
        buf += ch
    if buf.strip():
        parts.append(buf)
    return parts


def _strip_inline_comment(line: str) -> str:
    """Drop ` # comment` trailing portion, respecting simple quoted strings."""
    in_q = ""
    for i, ch in enumerate(line):
        if in_q:
            if ch == in_q:
                in_q = ""
            continue
        if ch in ('"', "'"):
            in_q = ch
            continue
        if ch == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i].rstrip()
    return line


def _tokenize(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for raw in text.splitlines():
        line = _strip_inline_comment(raw.rstrip())
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        out.append((indent, stripped))
    return out


def _parse(tokens: list[tuple[int, str]], pos: int, indent: int) -> tuple[Any, int]:
    if pos >= len(tokens):
        return None, pos
    cur_indent, body = tokens[pos]
    if cur_indent < indent:
        return None, pos
    if body.startswith("- "):
        return _parse_list(tokens, pos, cur_indent)
    return _parse_map(tokens, pos, cur_indent)


def _parse_list(tokens: list[tuple[int, str]], pos: int, indent: int) -> tuple[list, int]:
    items: list[Any] = []
    while pos < len(tokens):
        ci, body = tokens[pos]
        if ci < indent:
            break
        if ci > indent:
            break
        if not body.startswith("- "):
            break
        content = body[2:].rstrip()
        # Inline mapping starts ('- key: value' or '- key:'): treat as dict beginning.
        if ":" in content and not content.startswith('"'):
            head_key, _, head_val = content.partition(":")
            head_val = head_val.strip()
            item: dict[str, Any] = {}
            if head_val:
                # 'key: value' inline scalar
                # Look ahead for nested keys at indent+2
                item[head_key.strip()] = _scalar(head_val)
            else:
                # 'key:' followed by nested block
                nested, pos2 = _parse(tokens, pos + 1, indent + 2 + 2)
                # Note: the head_key's value is whatever sits below it.
                pos = pos2 - 1  # will increment below
                item[head_key.strip()] = nested
            pos += 1
            # Consume subsequent keys belonging to this list-item dict (indent = list-item content indent)
            content_indent = indent + 2
            while pos < len(tokens):
                ni, nb = tokens[pos]
                if ni < content_indent or nb.startswith("- "):
                    break
                if ni == content_indent and ":" in nb and not nb.startswith('"'):
                    key, _, val = nb.partition(":")
                    val = val.strip()
                    if val:
                        item[key.strip()] = _scalar(val)
                        pos += 1
                    else:
                        nested, pos2 = _parse(tokens, pos + 1, content_indent + 2)
                        item[key.strip()] = nested
                        pos = pos2
                else:
                    break
            items.append(item)
        else:
            items.append(_scalar(content))
            pos += 1
    return items, pos


def _parse_map(tokens: list[tuple[int, str]], pos: int, indent: int) -> tuple[dict, int]:
    out: dict[str, Any] = {}
    while pos < len(tokens):
        ci, body = tokens[pos]
        if ci < indent or body.startswith("- "):
            break
        if ci > indent:
            break
        if ":" not in body:
            break
        key, _, val = body.partition(":")
        key = key.strip()
        val = val.strip()
        if val == "" or val == "|":
            nested, pos2 = _parse(tokens, pos + 1, indent + 2)
            out[key] = nested if nested is not None else {}
            pos = pos2
        else:
            out[key] = _scalar(val)
            pos += 1
    return out, pos


def loads(text: str) -> Any:
    tokens = _tokenize(text)
    data, _ = _parse(tokens, 0, 0)
    return data


def load(path) -> Any:
    from pathlib import Path

    return loads(Path(path).read_text(encoding="utf-8"))
