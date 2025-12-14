"""Module-2 style composition: cited_by list + author metrics enrich + filtering."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pcra.openalex import OpenAlexClient
from pcra.openalex import authors as authors_api
from pcra.openalex.fields import AUTHOR_METRICS_SELECT
from pcra.openalex.utils import dedupe_preserve_order


def collect_author_ids_from_works(works: List[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    for w in works:
        for a in w.get("authors") or []:
            aid = a.get("author_id")
            if aid:
                ids.append(aid)
    return dedupe_preserve_order(ids)


def enrich_authors_with_h_index(
    works: List[Dict[str, Any]],
    *,
    client: OpenAlexClient,
    max_authors: Optional[int] = None,
    chunk_size: int = 50,
) -> List[Dict[str, Any]]:
    author_ids = collect_author_ids_from_works(works)
    if max_authors is not None:
        author_ids = author_ids[: max(0, max_authors)]
    if not author_ids:
        return works

    authors = authors_api.get_authors_by_openalex_ids(
        author_ids, client=client, select=AUTHOR_METRICS_SELECT, chunk_size=chunk_size
    )
    h_index_map: Dict[str, Optional[int]] = {}
    for aid, a in authors.items():
        summary = a.get("summary_stats") or {}
        h_index_map[aid] = summary.get("h_index") or a.get("h_index")

    for w in works:
        for a in w.get("authors") or []:
            aid = a.get("author_id")
            if aid and aid in h_index_map:
                a["h_index"] = h_index_map[aid]
    return works


def filter_works_by_h_index(
    works: List[Dict[str, Any]],
    *,
    h_index_threshold: int,
    h_index_first_author_threshold: int,
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for w in works:
        authors = w.get("authors") or []
        if not authors:
            continue
        h_values = [a.get("h_index") for a in authors if isinstance(a.get("h_index"), int)]
        max_h = max(h_values) if h_values else None
        first_author = None
        for a in authors:
            if a.get("author_position") == "first":
                first_author = a
                break
        if first_author is None:
            first_author = authors[0]
        first_h = first_author.get("h_index") if isinstance(first_author.get("h_index"), int) else None

        if (max_h is not None and max_h >= h_index_threshold) or (
            first_h is not None and first_h >= h_index_first_author_threshold
        ):
            filtered.append(w)
    return filtered
