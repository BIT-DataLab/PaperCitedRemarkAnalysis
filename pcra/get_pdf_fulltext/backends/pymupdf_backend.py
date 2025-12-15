"""Backend: extract PDF text via PyMuPDF (plain text)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

from .. import config


def extract_markdown(
    pdf_path: Path,
    *,
    truncate_long_pdf: bool = config.DEFAULT_TRUNCATE_LONG_PDF,
    max_pages: int = config.DEFAULT_MAX_PAGES,
) -> Tuple[str, Dict[str, Any]]:
    """Extract PDF content as plain text (treated as Markdown) via PyMuPDF.

    This backend bypasses "truncate then parse": it directly reads the first
    `max_pages` pages (when truncation is enabled) and extracts their text via
    `Page.get_text()`.

    Returns:
        (text, meta) where meta includes:
          - page_count: total pages in PDF
          - pages_used: pages actually parsed
          - truncated: whether pages were limited to max_pages
    """

    if max_pages <= 0:
        raise ValueError(f"max_pages must be > 0, got: {max_pages}")

    try:
        import fitz  # PyMuPDF
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Missing dependency: pymupdf (PyMuPDF). Install via: pip3 install --user pymupdf"
        ) from exc

    with fitz.open(str(pdf_path)) as doc:
        page_count = int(doc.page_count)
        pages_used = page_count
        truncated = False

        if truncate_long_pdf and page_count > max_pages:
            pages_used = int(max_pages)
            truncated = True

        parts = []
        for page_index in range(pages_used):
            page = doc.load_page(page_index)
            parts.append(page.get_text())

    text = "\n\n".join(parts)
    return text, {"page_count": page_count, "pages_used": pages_used, "truncated": truncated}

