"""Candidate selection rules for the refactored pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pcra.author.metrics import compute_max_h_index_author


def _max_h_index_value(candidate: Dict[str, Any]) -> int:
    author = candidate.get("max_h_index_author") or {}
    h = author.get("h_index")
    if isinstance(h, int):
        return h
    return 0


def _sort_key(candidate: Dict[str, Any]) -> Tuple[int, int, int, str]:
    max_h = _max_h_index_value(candidate)
    cited_by_count = candidate.get("cited_by_count") or 0
    year = candidate.get("year") or 0
    title = candidate.get("paper_title") or ""
    return (-max_h, -int(cited_by_count), -int(year), str(title))


def ensure_max_h_index_author(candidate: Dict[str, Any]) -> None:
    if candidate.get("max_h_index_author") is not None:
        return
    authors = candidate.get("authors") or []
    candidate["max_h_index_author"] = compute_max_h_index_author(authors)


def select_candidates(
    cited_by_enriched: List[Dict[str, Any]],
    *,
    roll_back_paper_topK: Optional[int],
) -> List[Dict[str, Any]]:
    published: List[Dict[str, Any]] = []
    for cand in cited_by_enriched:
        status = ((cand.get("publication_status") or {}).get("status") or "").lower()
        if status == "published":
            ensure_max_h_index_author(cand)
            published.append(cand)

    primary = [c for c in published if c.get("has_fellow_topk")]
    if primary:
        for c in primary:
            c["selection_reason"] = "primary"
        return primary

    fallback = sorted(published, key=_sort_key)
    if roll_back_paper_topK is not None:
        fallback = fallback[: max(0, int(roll_back_paper_topK))]
    for c in fallback:
        c["selection_reason"] = "fallback"
    return fallback
