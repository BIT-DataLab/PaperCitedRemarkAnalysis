"""Top-level facade for fetching paper PDFs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional, Tuple

from . import cache
from . import config
from .download import build_pdf_filename, download_pdf
from .duckduckgo import search_duckduckgo
from .pdf_resolver import (
    fetch_pdf_url_from_page_url,
    find_pdf_for_result,
    title_is_relevant,
)

logger = logging.getLogger(__name__)


def _normalize_paper_id(paper_id: Optional[str]) -> str:
    value = (paper_id or "").strip()
    return value or "unknown"


def _resolve_cached_pdf(
    paper_id: str,
    paper_title: str,
    *,
    dest_dir: Path,
    cache_path: Path,
) -> Optional[Path]:
    cached = cache.get_cached_entry(cache.load_cache(cache_path), paper_id)
    if cached:
        cached_path = Path(cached.get("path") or "")
        if cached_path.exists():
            return cached_path
    expected = dest_dir / build_pdf_filename(paper_id, paper_title)
    if expected.exists():
        cache.update_cache_entry(
            cache_path,
            paper_id,
            {
                "paper_title": paper_title,
                "filename": expected.name,
                "path": str(expected),
                "status": "hit",
            },
        )
        return expected
    return None


def process_search_results(
    query: str,
    results: Iterable[Tuple[str, str]],
    *,
    paper_id: str,
    paper_title: str,
    dest_dir: Optional[Path] = None,
    cache_path: Optional[Path] = None,
) -> Optional[Path]:
    dest_dir = dest_dir if dest_dir is not None else config.downloads_dir()
    cache_path = cache_path if cache_path is not None else config.pdf_cache_path()
    for title, url in results:
        if not title_is_relevant(title, query):
            logger.debug("Skip low-relevance result: %s", title)
            continue

        logger.info("Process result: %s -> %s", title, url)
        pdf_url = find_pdf_for_result(title=title, url=url, query=query)
        if not pdf_url:
            continue
        try:
            saved_to = download_pdf(
                pdf_url,
                paper_id,
                paper_title,
                dest_dir=dest_dir,
                cache_path=cache_path,
                meta={"query": query, "result_title": title},
            )
            logger.info("Saved PDF to: %s", saved_to)
            return saved_to
        except Exception as exc:
            logger.info("Download failed %s: %s", pdf_url, exc)
            continue

    logger.info("No usable PDF link found.")
    return None


def search_and_download(
    query: str,
    *,
    engine: str = "duckduckgo",
    paper_id: Optional[str] = None,
    paper_title: Optional[str] = None,
    dest_dir: Optional[Path] = None,
    cache_path: Optional[Path] = None,
) -> Optional[Path]:
    if engine != "duckduckgo":
        raise ValueError(f"Unsupported engine: {engine}")
    dest_dir = dest_dir if dest_dir is not None else config.downloads_dir()
    cache_path = cache_path if cache_path is not None else config.pdf_cache_path()
    normalized_id = _normalize_paper_id(paper_id)
    resolved_title = paper_title or query
    cached = _resolve_cached_pdf(
        normalized_id,
        resolved_title,
        dest_dir=dest_dir,
        cache_path=cache_path,
    )
    if cached:
        return cached
    results = search_duckduckgo(query)
    return process_search_results(
        query,
        results,
        paper_id=normalized_id,
        paper_title=resolved_title,
        dest_dir=dest_dir,
        cache_path=cache_path,
    )


def fetch_pdf_from_url(
    url: str,
    query: str,
    *,
    paper_id: Optional[str] = None,
    paper_title: Optional[str] = None,
    dest_dir: Optional[Path] = None,
    cache_path: Optional[Path] = None,
) -> Optional[Path]:
    dest_dir = dest_dir if dest_dir is not None else config.downloads_dir()
    cache_path = cache_path if cache_path is not None else config.pdf_cache_path()
    normalized_id = _normalize_paper_id(paper_id)
    resolved_title = paper_title or query
    cached = _resolve_cached_pdf(
        normalized_id,
        resolved_title,
        dest_dir=dest_dir,
        cache_path=cache_path,
    )
    if cached:
        return cached
    pdf_url = fetch_pdf_url_from_page_url(url, query)
    if not pdf_url:
        return None
    return download_pdf(
        pdf_url,
        normalized_id,
        resolved_title,
        dest_dir=dest_dir,
        cache_path=cache_path,
        meta={"query": query, "source_page": url},
    )
