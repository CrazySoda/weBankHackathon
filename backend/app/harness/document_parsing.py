"""Document parsing: PDF/image → text spans with coordinates (for evidence).

Pure extraction with PyMuPDF; returns spans the LLM only *labellers*, never
modifies. Also exposes the hidden-text detector used by injection_screen.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextSpan:
    page: int
    bbox: tuple[float, float, float, float]
    text: str
    color: int  # sRGB int from PyMuPDF span color


def parse_pdf_spans(pdf_bytes: bytes) -> list[TextSpan]:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        spans: list[TextSpan] = []
        for pno, page in enumerate(doc):
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        spans.append(
                            TextSpan(
                                page=pno,
                                bbox=tuple(span["bbox"]),
                                text=span["text"],
                                color=span.get("color", 0),
                            )
                        )
        return spans
    finally:
        doc.close()


def render_pdf_pages(pdf_bytes: bytes, max_pages: int = 3, zoom: float = 2.0) -> list[bytes]:
    """PNG images of the first pages, for a vision model (scanned PDFs have no text layer)."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return [
            page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
            for page in list(doc)[:max_pages]
        ]
    finally:
        doc.close()


def full_text(spans: list[TextSpan]) -> str:
    return "\n".join(s.text for s in spans)


def find_hidden_text(spans: list[TextSpan], page_bg_is_light: bool = True) -> list[TextSpan]:
    """Spans rendered white (or near-white) on a light page — classic hiding."""
    if not page_bg_is_light:
        return []
    out = []
    for s in spans:
        r, g, b = (s.color >> 16) & 0xFF, (s.color >> 8) & 0xFF, s.color & 0xFF
        if r > 0xF0 and g > 0xF0 and b > 0xF0 and s.text.strip():
            out.append(s)
    return out
