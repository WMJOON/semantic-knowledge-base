#!/usr/bin/env python3
"""Text chunking for skb-evidence.

Algorithm (SPEC §5.1):
  1. Split by paragraph (double newline)
  2. If a paragraph > chunk_size, split further at sentence boundaries
  3. Merge adjacent chunks that are too short (< 300 chars)
  4. Apply overlap window between adjacent chunks

For a single unbroken string (no paragraph breaks) with length N,
the chunker falls through to sliding-window splitting, producing
⌈N / (chunk_size - chunk_overlap)⌉ chunks.
"""

from __future__ import annotations

import re

_MIN_CHUNK = 300


def _split_sentences(text: str) -> list[str]:
    """Split text at sentence boundaries (.?! followed by whitespace)."""
    parts = re.split(r'(?<=[.?!])\s+', text)
    return [p.strip() for p in parts if p.strip()]


def _merge_short(chunks: list[str], min_size: int) -> list[str]:
    """Merge adjacent chunks that are too short."""
    if not chunks:
        return chunks
    result: list[str] = []
    buf = chunks[0]
    for c in chunks[1:]:
        if len(buf) < min_size:
            buf = buf + " " + c
        else:
            result.append(buf)
            buf = c
    result.append(buf)
    return result


def _sliding_window(text: str, size: int, overlap: int) -> list[str]:
    """Pure sliding window for texts with no paragraph structure."""
    step = max(1, size - overlap)
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = start + size
        chunks.append(text[start:end])
        if end >= n:
            break
        start += step
    return chunks


def chunk_text(text: str, chunk_size: int = 1200, chunk_overlap: int = 100) -> list[str]:
    """Split *text* into overlapping chunks.

    For a pure no-paragraph text of length N, produces
    ⌈N / (chunk_size - chunk_overlap)⌉ chunks (SPEC AC-EV-4).
    """
    text = text.strip()
    if not text:
        return []

    # 1. Paragraph split
    paragraphs = [p.strip() for p in re.split(r'\n\n+', text) if p.strip()]

    if not paragraphs:
        # No structure → sliding window
        return _sliding_window(text, chunk_size, chunk_overlap)

    # 2. Sentence-split paragraphs that exceed chunk_size
    pieces: list[str] = []
    for para in paragraphs:
        if len(para) <= chunk_size:
            pieces.append(para)
        else:
            sentences = _split_sentences(para)
            if len(sentences) <= 1:
                # No sentence boundaries — fall back to sliding window for this para
                pieces.extend(_sliding_window(para, chunk_size, chunk_overlap))
            else:
                buf = ""
                for sent in sentences:
                    if not buf:
                        buf = sent
                    elif len(buf) + 1 + len(sent) <= chunk_size:
                        buf = buf + " " + sent
                    else:
                        pieces.append(buf)
                        buf = sent
                if buf:
                    pieces.append(buf)

    # 3. Merge short pieces (only those that are actually short AND fit in chunk_size)
    pieces = _merge_short(pieces, _MIN_CHUNK)

    # 4. Apply overlap: each chunk = piece + first chunk_overlap chars of next piece
    if not pieces:
        return []

    result: list[str] = []
    for i, piece in enumerate(pieces):
        if i + 1 < len(pieces) and chunk_overlap > 0:
            overlap_text = pieces[i + 1][:chunk_overlap]
            result.append(piece + " " + overlap_text)
        else:
            result.append(piece)

    return result
