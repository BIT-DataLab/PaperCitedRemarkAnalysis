"""OpenAlex Works resource API (single-entity operations, no cross-entity enrich)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import OpenAlexClient
from .fields import (
    DEFAULT_CITED_BY_SORT,
    MAX_PER_PAGE,
    WORK_CITED_BY_SELECT,
    WORK_MATCH_SELECT,
    WORK_META_SELECT,
)
from .utils import to_short_openalex_id


def search_works_by_title(
    title: str,
    *,
    client: OpenAlexClient,
    per_page: int = 3,
    select: str = WORK_MATCH_SELECT,
) -> List[Dict[str, Any]]:
    params = {"search": title, "per-page": per_page, "select": select}
    data = client.get_json("/works", params=params)
    return data.get("results") or []


def get_work(
    work_id: str,
    *,
    client: OpenAlexClient,
    select: str = WORK_META_SELECT,
) -> Dict[str, Any]:
    short_id = to_short_openalex_id(work_id) or work_id
    params = {"select": select} if select else None
    return client.get_json(f"/works/{short_id}", params=params)


def list_citing_works(
    work_id: str,
    *,
    client: OpenAlexClient,
    per_page: int = 20,
    select: str = WORK_CITED_BY_SELECT,
    sort: str = DEFAULT_CITED_BY_SORT,
) -> List[Dict[str, Any]]:
    short_id = to_short_openalex_id(work_id) or work_id
    params: Dict[str, Any] = {
        "filter": f"cites:{short_id}",
        "per-page": per_page,
    }
    if select:
        params["select"] = select
    if sort:
        params["sort"] = sort
    data = client.get_json("/works", params=params)
    return data.get("results") or []


def list_citing_works_filtered(
    work_id: str,
    *,
    client: OpenAlexClient,
    filter_expr: Optional[str] = None,
    per_page: int = MAX_PER_PAGE,
    select: str = WORK_CITED_BY_SELECT,
    sort: Optional[str] = None,
    max_pages: Optional[int] = None,
) -> List[Dict[str, Any]]:
    short_id = to_short_openalex_id(work_id) or work_id
    filters = [f"cites:{short_id}"]
    if filter_expr:
        filters.append(filter_expr)
    params: Dict[str, Any] = {"filter": ",".join(filters)}
    if select:
        params["select"] = select
    if sort:
        params["sort"] = sort
    per_page = min(MAX_PER_PAGE, max(1, int(per_page)))
    results: List[Dict[str, Any]] = []
    for item in client.iter_cursor("/works", params=params, per_page=per_page, max_pages=max_pages):
        results.append(item)
    return results


def get_works_by_openalex_ids(
    work_ids: List[str],
    *,
    client: OpenAlexClient,
    select: str = WORK_MATCH_SELECT,
    chunk_size: int = 50,
) -> Dict[str, Dict[str, Any]]:
    """Bulk fetch works via `filter=openalex_id:W1|W2|...` (chunked)."""
    out: Dict[str, Dict[str, Any]] = {}
    ids = [to_short_openalex_id(x) for x in work_ids]
    ids = [x for x in ids if x]
    for i in range(0, len(ids), max(1, chunk_size)):
        chunk = ids[i : i + chunk_size]
        params: Dict[str, Any] = {
            "filter": "openalex_id:" + "|".join(chunk),
            "per-page": min(len(chunk), 200),
        }
        if select:
            params["select"] = select
        data = client.get_json("/works", params=params)
        for item in data.get("results") or []:
            sid = to_short_openalex_id(item.get("id"))
            if sid:
                out[sid] = item
    return out
