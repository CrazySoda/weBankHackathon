#!/usr/bin/env python
"""Generate the deterministic PDF seed corpora (BUILD_PLAN M3).

Reads ``seed/deals/deals.json`` and writes one PDF per document to
``seed/deals/pdfs/<deal_id>/<filename>``. With ``--poisoned`` it instead reads
``seed/poisoned/poisoned.json`` and writes the poisoned suite to
``seed/deals/pdfs/poisoned/<doc_id>.pdf``, rendering ``hidden_text`` lines in
white so ``find_hidden_text`` (and therefore the injection_screen rules) sees
them as hidden white-on-light text.

Deterministic: fixed page geometry, font, metadata and no timestamps, so two
runs over the same input produce byte-identical files. Run with:

    cd backend && uv run python -I seed/generate_seed_docs.py [--poisoned]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SEED_DIR = Path(__file__).resolve().parent
DEALS_JSON = SEED_DIR / "deals" / "deals.json"
POISONED_JSON = SEED_DIR / "poisoned" / "poisoned.json"
DEFAULT_OUT = SEED_DIR / "deals" / "pdfs"

PAGE_WIDTH, PAGE_HEIGHT = 595, 842  # A4 portrait in points
MARGIN = 72
LINE_HEIGHT = 16
FONT_NAME = "helv"
FONT_NAME_CJK = "china-s"  # built-in simplified-Chinese font for CN attack lines
FONT_SIZE = 11

# Fixed metadata: no clock reads, so output bytes are reproducible.
FIXED_METADATA = {
    "creator": "cleartrade-seed",
    "producer": "cleartrade-seed",
    "author": "cleartrade-seed",
    "title": "ClearTrade synthetic seed document",
    "subject": "synthetic",
    "keywords": "cleartrade,synthetic,seed",
    "creationDate": "D:20260101000000Z",
    "modDate": "D:20260101000000Z",
}


def load_pymupdf():
    """Import PyMuPDF preferring the canonical ``pymupdf`` name."""
    try:
        import pymupdf  # type: ignore[import-not-found]

        return pymupdf
    except ImportError:  # pragma: no cover - older PyMuPDF installs
        import fitz  # type: ignore[import-not-found]

        return fitz


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def render_pdf(pymupdf: Any, lines: list[str], white_lines: list[str], path: Path) -> None:
    """Write one PDF: each line at a fixed position, ``white_lines`` in white.

    A line is rendered white only if it appears in ``white_lines``; this keeps
    visible text black even when a poisoned spec repeats a phrase.
    """
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        y = MARGIN
        for line in lines + white_lines:
            color = (1, 1, 1) if line in white_lines else (0, 0, 0)
            # Helvetica cannot encode CJK; use the built-in CN font so the
            # Chinese instruction patterns survive extraction intact
            font = FONT_NAME_CJK if any(ord(ch) > 0x7F for ch in line) else FONT_NAME
            page.insert_text((MARGIN, y), line, fontname=font, fontsize=FONT_SIZE, color=color)
            y += LINE_HEIGHT
        doc.set_metadata(FIXED_METADATA)
        path.parent.mkdir(parents=True, exist_ok=True)
        # no_new_id: PyMuPDF otherwise mints a random PDF /ID per save, which
        # would make the output non-reproducible
        doc.save(str(path), deflate=True, no_new_id=True)
    finally:
        doc.close()


def generate_deals(pymupdf: Any, out_dir: Path) -> list[Path]:
    data = load_json(DEALS_JSON)
    written: list[Path] = []
    for deal in data["deals"]:
        for document in deal["documents"]:
            fields: dict[str, str] = document["fields"]
            lines = [f"{name}: {value}" for name, value in fields.items()]
            path = out_dir / deal["deal_id"] / document["filename"]
            render_pdf(pymupdf, lines, [], path)
            written.append(path)
    return written


def generate_poisoned(pymupdf: Any, out_dir: Path) -> list[Path]:
    data = load_json(POISONED_JSON)
    written: list[Path] = []
    for spec in data["documents"]:
        visible: list[str] = spec["visible_text"]
        hidden: list[str] = spec.get("hidden_text", [])
        path = out_dir / "poisoned" / f"{spec['doc_id']}.pdf"
        render_pdf(pymupdf, visible, hidden, path)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic seed PDFs.")
    parser.add_argument(
        "--poisoned",
        action="store_true",
        help="generate the poisoned document suite instead of the deal documents",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"output directory (default: {DEFAULT_OUT})",
    )
    args = parser.parse_args(argv)

    pymupdf = load_pymupdf()
    if args.poisoned:
        written = generate_poisoned(pymupdf, args.out)
    else:
        written = generate_deals(pymupdf, args.out)

    for path in written:
        sys.stdout.write(f"wrote {path}\n")
    sys.stdout.write(f"total: {len(written)} PDF(s)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
