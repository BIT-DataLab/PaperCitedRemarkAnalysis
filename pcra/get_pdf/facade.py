"""Top-level facade for fetching paper PDFs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional, Tuple

from . import config
from .download import download_pdf
from .duckduckgo import search_duckduckgo
from .pdf_resolver import (
    fetch_pdf_url_from_page_url,
    find_pdf_for_result,
    title_is_relevant,
)

logger = logging.getLogger(__name__)


def process_search_results(query: str, results: Iterable[Tuple[str, str]]) -> Optional[Path]:
    for title, url in results:
        if not title_is_relevant(title, query):
            logger.debug("Skip low-relevance result: %s", title)
            continue

        logger.info("Process result: %s -> %s", title, url)
        pdf_url = find_pdf_for_result(title=title, url=url, query=query)
        if not pdf_url:
            continue
        try:
            saved_to = download_pdf(pdf_url, title)
            logger.info("Saved PDF to: %s", saved_to)
            return saved_to
        except Exception as exc:
            logger.info("Download failed %s: %s", pdf_url, exc)
            continue

    logger.info("No usable PDF link found.")
    return None


def search_and_download(query: str, engine: str = "duckduckgo") -> Optional[Path]:
    if engine != "duckduckgo":
        raise ValueError(f"Unsupported engine: {engine}")
    results = search_duckduckgo(query)
    return process_search_results(query, results)


def fetch_pdf_from_url(url: str, query: str) -> Optional[Path]:
    pdf_url = fetch_pdf_url_from_page_url(url, query)
    if not pdf_url:
        return None
    return download_pdf(pdf_url, query, dest_dir=config.downloads_dir())

