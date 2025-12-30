"""Top-level facade for extracting in-text citation contexts by reference title."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from . import config
from .citations import extract_author_year_citation_contexts, extract_citation_contexts
from .match import find_reference_entry_by_title
from .references import parse_reference_entries, split_body_and_references

logger = logging.getLogger(__name__)


def _clean_reference_entry_for_output(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def get_paper_reference_context(
    md_text: str,
    title: str,
    *,
    window: int = config.DEFAULT_WINDOW,
    match_threshold: float = config.DEFAULT_MATCH_THRESHOLD,
    citation_style: str = "auto",
) -> Dict[str, Any]:
    """High-level API: title -> ref_id -> in-text contexts.

    Notes:
        - Supports both Markdown (e.g. from pymupdf4llm) and plain text (e.g. from PyMuPDF).
        - If References/Bibliography heading is not found, returns an empty result with an `error`
          field and logs a warning.
        - citation_style can be "auto" (default), "numeric", or "author_year".
    """

    base: Dict[str, Any] = {
        "query_title": title,
        "ref_id": None,
        "match_score": 0.0,
        "reference_entry": None,
        "contexts": [],
        "error": None,
        "citation_style_detected": None,
        "author_year_key": None,
        "debug": {
            "ref_entry_parse_method": None,
            "num_entries": 0,
            "has_numeric_ids": False,
            "locator_used": [],
            "errors": [],
        },
    }

    try:
        body, references = split_body_and_references(md_text)
    except ValueError as e:
        msg = str(e)
        logger.warning("pcra.get_ref_ctx: %s", msg)
        base["error"] = msg
        return base

    if citation_style not in {"auto", "numeric", "author_year"}:
        raise ValueError(f"citation_style must be auto|numeric|author_year, got: {citation_style!r}")

    entries, parse_meta = parse_reference_entries(references, return_meta=True)
    base["debug"]["ref_entry_parse_method"] = parse_meta.get("method")
    base["debug"]["has_numeric_ids"] = bool(parse_meta.get("has_numeric_ids"))
    base["debug"]["num_entries"] = len(entries)
    if not entries:
        base["debug"]["errors"].append("no_reference_entries")
        return base
    match = find_reference_entry_by_title(entries, title, match_threshold=match_threshold)
    if match is None:
        base["debug"]["errors"].append("title_match_failed")
        return base

    entry = match.entry
    ref_id = entry.ref_id
    year_with_suffix = None
    author_year_key = None
    if entry.first_author and entry.year:
        year_with_suffix = entry.year + (entry.year_suffix or "")
        author_year_key = f"{entry.first_author}|{year_with_suffix}"

    contexts = []
    locator_used: List[str] = []
    numeric_available = bool(parse_meta.get("has_numeric_ids"))
    author_year_available = bool(entry.first_author and entry.year and year_with_suffix)

    if citation_style in {"auto", "numeric"} and numeric_available:
        locator_used.append("numeric")
        contexts.extend(extract_citation_contexts(body, ref_id, window=window))

    if citation_style in {"auto", "author_year"} and author_year_available:
        locator_used.append("author_year")
        contexts.extend(
            extract_author_year_citation_contexts(
                body,
                ref_id=ref_id,
                surname=entry.first_author or "",
                year_with_suffix=year_with_suffix or "",
                window=window,
            )
        )

    if not locator_used:
        base["debug"]["errors"].append("no_locator_available")

    deduped: List[Any] = []
    seen = set()
    for c in contexts:
        key = (c.start, c.end, c.match_text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)

    if len(locator_used) == 1:
        base["citation_style_detected"] = locator_used[0]
    elif len(locator_used) == 2:
        base["citation_style_detected"] = "mixed"
    base["author_year_key"] = author_year_key
    base["debug"]["locator_used"] = locator_used
    base.update(
        {
            "ref_id": ref_id,
            "match_score": match.score,
            "reference_entry": _clean_reference_entry_for_output(entry.raw_text),
            "contexts": [
                {
                    "ref_id": c.ref_id,
                    "match_text": c.match_text,
                    "start": c.start,
                    "end": c.end,
                    "line": c.line,
                    "col": c.col,
                    "context": c.context,
                }
                for c in deduped
            ],
        }
    )
    return base
