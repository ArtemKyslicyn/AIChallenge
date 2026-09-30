"""Two chunking strategies: fixed window and structural (headings/files)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    text: str
    source: str
    title: str
    section: str
    strategy: str
    index: int


_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _chunk_id(source: str, strategy: str, index: int, text: str) -> str:
    digest = hashlib.sha1(f"{source}|{strategy}|{index}|{text[:64]}".encode()).hexdigest()[:12]
    return f"{strategy}-{digest}"


def chunk_fixed(
    text: str,
    *,
    source: str,
    title: str,
    size: int = 800,
    overlap: int = 120,
) -> list[Chunk]:
    cleaned = text.strip()
    if not cleaned:
        return []
    size = max(64, size)
    overlap = max(0, min(overlap, size // 2))
    chunks: list[Chunk] = []
    start = 0
    index = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + size)
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(
                Chunk(
                    chunk_id=_chunk_id(source, "fixed", index, piece),
                    text=piece,
                    source=source,
                    title=title,
                    section=f"offset-{start}",
                    strategy="fixed",
                    index=index,
                )
            )
            index += 1
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def chunk_structural(text: str, *, source: str, title: str) -> list[Chunk]:
    cleaned = text.strip()
    if not cleaned:
        return []
    matches = list(_HEADING.finditer(cleaned))
    if not matches:
        # No headings — fall back to coarse paragraphs (~fixed without overlap).
        parts = [p.strip() for p in re.split(r"\n{2,}", cleaned) if p.strip()]
        if not parts:
            parts = [cleaned]
        out: list[Chunk] = []
        for i, part in enumerate(parts):
            # Keep structural chunks bounded.
            if len(part) > 1600:
                for sub in chunk_fixed(part, source=source, title=title, size=900, overlap=80):
                    out.append(
                        Chunk(
                            chunk_id=_chunk_id(source, "structural", len(out), sub.text),
                            text=sub.text,
                            source=source,
                            title=title,
                            section=f"para-{i}",
                            strategy="structural",
                            index=len(out),
                        )
                    )
            else:
                out.append(
                    Chunk(
                        chunk_id=_chunk_id(source, "structural", len(out), part),
                        text=part,
                        source=source,
                        title=title,
                        section=f"para-{i}",
                        strategy="structural",
                        index=len(out),
                    )
                )
        return out

    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        preamble = cleaned[: matches[0].start()].strip()
        if preamble:
            sections.append(("(preamble)", preamble))
    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned)
        body = cleaned[body_start:body_end].strip()
        block = f"{match.group(0).strip()}\n{body}".strip()
        sections.append((heading, block))

    out = []
    for i, (section, block) in enumerate(sections):
        if len(block) > 1800:
            for sub in chunk_fixed(block, source=source, title=title, size=900, overlap=80):
                out.append(
                    Chunk(
                        chunk_id=_chunk_id(source, "structural", len(out), sub.text),
                        text=sub.text,
                        source=source,
                        title=title,
                        section=section,
                        strategy="structural",
                        index=len(out),
                    )
                )
        else:
            out.append(
                Chunk(
                    chunk_id=_chunk_id(source, "structural", len(out), block),
                    text=block,
                    source=source,
                    title=title,
                    section=section,
                    strategy="structural",
                    index=len(out),
                )
            )
    return out


def chunk_document(
    text: str,
    *,
    source: str,
    title: str,
    strategy: str,
    fixed_size: int = 800,
    fixed_overlap: int = 120,
) -> list[Chunk]:
    if strategy == "fixed":
        return chunk_fixed(
            text, source=source, title=title, size=fixed_size, overlap=fixed_overlap
        )
    return chunk_structural(text, source=source, title=title)
