"""Utilities for truncating long PDFs before parsing."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Iterator, Tuple


def get_page_count(pdf_path: Path) -> int:
    """Return total pages for a PDF."""
    try:
        import fitz  # PyMuPDF
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Missing dependency: pymupdf (PyMuPDF). Install via: pip3 install --user pymupdf"
        ) from exc

    with fitz.open(str(pdf_path)) as doc:
        return int(doc.page_count)


def truncate_pdf_first_n_pages(pdf_path: Path, out_path: Path, *, max_pages: int) -> int:
    """Write a new PDF containing only the first `max_pages` pages.

    Returns:
        pages_written
    """
    if max_pages <= 0:
        raise ValueError(f"max_pages must be > 0, got: {max_pages}")

    try:
        import fitz  # PyMuPDF
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Missing dependency: pymupdf (PyMuPDF). Install via: pip3 install --user pymupdf"
        ) from exc

    with fitz.open(str(pdf_path)) as src:
        total = int(src.page_count)
        pages_written = min(total, max_pages)
        if pages_written <= 0:
            raise ValueError(f"PDF has no pages: {pdf_path}")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with fitz.open() as dst:
            dst.insert_pdf(src, from_page=0, to_page=pages_written - 1)
            dst.save(str(out_path))
        return pages_written


@contextmanager
def open_maybe_truncated_pdf(
    pdf_path: Path,
    *,
    enabled: bool,
    max_pages: int,
) -> Iterator[Tuple[Path, Dict[str, object]]]:
    """Yield a PDF path that may be truncated to the first `max_pages` pages.

    When truncation is applied, the yielded path points to a temporary file that
    is deleted when the context exits.
    """
    page_count = get_page_count(pdf_path)
    if enabled and page_count > max_pages:
        with TemporaryDirectory(prefix="pcra_pdf_trunc_") as tmpdir:
            out_path = Path(tmpdir) / f"{pdf_path.stem}.p0-{max_pages}.pdf"
            pages_written = truncate_pdf_first_n_pages(pdf_path, out_path, max_pages=max_pages)
            yield out_path, {
                "page_count": page_count,
                "pages_used": pages_written,
                "truncated": True,
                "parsed_pdf": str(out_path),
            }
    else:
        yield pdf_path, {
            "page_count": page_count,
            "pages_used": page_count,
            "truncated": False,
            "parsed_pdf": str(pdf_path),
        }

