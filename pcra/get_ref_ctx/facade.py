"""Top-level facade for extracting in-text citation contexts by reference title."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict

from . import config
from .citations import extract_citation_contexts
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
) -> Dict[str, Any]:
    """High-level API: title -> ref_id -> in-text contexts.

    Notes:
        - Supports both Markdown (e.g. from pymupdf4llm) and plain text (e.g. from PyMuPDF).
        - If References/Bibliography heading is not found, returns an empty result with an `error`
          field and logs a warning.
    """

    base: Dict[str, Any] = {
        "query_title": title,
        "ref_id": None,
        "match_score": 0.0,
        "reference_entry": None,
        "contexts": [],
        "error": None,
    }

    try:
        body, references = split_body_and_references(md_text)
    except ValueError as e:
        msg = str(e)
        logger.warning("pcra.get_ref_ctx: %s", msg)
        base["error"] = msg
        return base

    entries = parse_reference_entries(references)
    match = find_reference_entry_by_title(entries, title, match_threshold=match_threshold)
    if match is None:
        return base

    contexts = extract_citation_contexts(body, match.entry.ref_id, window=window)
    base.update(
        {
            "ref_id": match.entry.ref_id,
            "match_score": match.score,
            "reference_entry": _clean_reference_entry_for_output(match.entry.raw_text),
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
                for c in contexts
            ],
        }
    )
    return base
