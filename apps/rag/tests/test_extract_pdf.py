"""PDF extraction must never index raw PDF object streams."""

from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

from aichallenge_rag.pipeline import extract_text, looks_like_pdf_garbage


def _pdf_with_text(phrase: str) -> bytes:
    """Build a tiny one-page PDF that contains ``phrase`` as extractable text."""
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=200)
    page = writer.pages[0]
    # Draw text via a content stream (Helvetica).
    content = DecodedStreamObject()
    safe = phrase.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content.set_data(f"BT /F1 12 Tf 40 140 Td ({safe}) Tj ET".encode("latin-1", errors="replace"))
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    resources = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = content
    page[NameObject("/MediaBox")] = DictionaryObject()  # keep writer happy
    # MediaBox already set by blank page; overwrite Contents only.
    page[NameObject("/Contents")] = content
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_looks_like_pdf_garbage_detects_raw_objects() -> None:
    raw = "%PDF-1.3\n1 0 obj\n<< /BaseFont /Helvetica >>\nendobj\n"
    assert looks_like_pdf_garbage(raw)


def test_extract_text_pdf_returns_phrase_not_header() -> None:
    data = _pdf_with_text("Orange widget day23 sample")
    text = extract_text(Path("sample.pdf"), raw=data)
    assert text
    assert not looks_like_pdf_garbage(text)
    assert "Orange widget" in text or "widget" in text.lower()


def test_extract_text_never_returns_raw_pdf_bytes_as_utf8() -> None:
    """Even a broken PDF must not become indexed %PDF object soup."""
    junk = b"%PDF-1.3\n1 0 obj<< /Length 9 >>stream\nNOTATEXT\nendstream\nendobj\n"
    text = extract_text(Path("broken.pdf"), raw=junk)
    assert text == "" or not looks_like_pdf_garbage(text)
    assert not (text or "").lstrip().startswith("%PDF")
