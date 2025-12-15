"""Unified facade for extracting paper fulltext from a PDF."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from . import config

PdfPath = Union[str, Path]


def _normalize_method(method: str) -> str:
    m = (method or "").strip().lower()
    if m in {"pymupdf", "pymupdf_text"}:
        return "pymupdf"
    if m in {"pymupdfllm", "pymupdf4llm"}:
        return "pymupdfllm"
    if m in {"mineru", "miner_u", "miner"}:
        return "mineru"
    raise ValueError(f"Unsupported method: {method!r}. Supported: {', '.join(config.SUPPORTED_METHODS)}")


def get_pdf_fulltext(
    pdf_path: PdfPath,
    *,
    method: str = config.DEFAULT_METHOD,
    truncate_long_pdf: bool = config.DEFAULT_TRUNCATE_LONG_PDF,
    max_pages: int = config.DEFAULT_MAX_PAGES,
    # MinerU-only options
    mineru_url: str = config.DEFAULT_MINERU_URL,
    mineru_lang_list: Optional[List[str]] = None,
    mineru_backend: str = config.DEFAULT_MINERU_BACKEND,
    mineru_timeout_s: int = config.DEFAULT_MINERU_TIMEOUT_S,
    # pymupdf4llm-only options
    pymupdfllm_write_images: bool = False,
    pymupdfllm_image_dir: Optional[PdfPath] = None,
) -> Dict[str, Any]:
    """Extract fulltext from a PDF with a selectable backend.

    Returns:
        dict with at least:
          - text: extracted fulltext (Markdown)
          - pages_used: number of PDF pages parsed
          - text_length: len(text)
    """

    pdf_path = Path(pdf_path).expanduser()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if max_pages <= 0:
        raise ValueError(f"max_pages must be > 0, got: {max_pages}")

    method = _normalize_method(method)
    started = time.time()

    if method == "pymupdf":
        from .backends.pymupdf_backend import extract_markdown as _extract_pymupdf

        text, extract_meta = _extract_pymupdf(
            pdf_path,
            truncate_long_pdf=truncate_long_pdf,
            max_pages=max_pages,
        )
        meta: Dict[str, object] = {
            "page_count": extract_meta.get("page_count"),
            "pages_used": extract_meta.get("pages_used"),
            "truncated": extract_meta.get("truncated"),
            "parsed_pdf": str(pdf_path),
        }
        backend_meta = {}
    else:
        from .truncate import open_maybe_truncated_pdf

        with open_maybe_truncated_pdf(pdf_path, enabled=truncate_long_pdf, max_pages=max_pages) as (parse_path, meta):
            if method == "pymupdfllm":
                from .backends.pymupdfllm_backend import extract_markdown as _extract_pymupdfllm

                text = _extract_pymupdfllm(
                    parse_path,
                    write_images=pymupdfllm_write_images,
                    image_dir=(Path(pymupdfllm_image_dir).expanduser() if pymupdfllm_image_dir else None),
                )
                backend_meta = {}
            elif method == "mineru":
                from .backends.mineru_backend import extract_markdown as _extract_mineru

                text, backend_meta = _extract_mineru(
                    parse_path,
                    url=mineru_url,
                    lang_list=mineru_lang_list,
                    backend=mineru_backend,
                    timeout_s=mineru_timeout_s,
                )
            else:
                raise ValueError(f"Unsupported method: {method!r}")

    elapsed_s = time.time() - started
    return {
        "text": text,
        "pages_used": meta["pages_used"],
        "text_length": len(text),
        "method": method,
        "truncated": meta["truncated"],
        "page_count": meta.get("page_count"),
        "source_pdf": str(pdf_path),
        "parsed_pdf": str(meta.get("parsed_pdf") or pdf_path),
        "elapsed_s": elapsed_s,
        "backend_meta": backend_meta,
    }
