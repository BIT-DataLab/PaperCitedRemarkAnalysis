"""OpenAlex Authors resource API (single-entity operations, no cross-entity enrich)."""

from __future__ import annotations

from typing import Any, Dict, List

from .client import OpenAlexClient
from .fields import (
    AUTHOR_MATCH_SELECT,
    AUTHOR_META_SELECT,
    AUTHOR_METRICS_SELECT,
    AUTHOR_TOP_WORKS_SELECT,
    DEFAULT_AUTHOR_WORKS_SORT,
)
from .utils import to_short_openalex_id


def search_authors_by_name(
    name: str,
    *,
    client: OpenAlexClient,
    per_page: int = 3,
    select: str = AUTHOR_MATCH_SELECT,
) -> List[Dict[str, Any]]:
    params = {"search": name, "per-page": per_page, "select": select}
    data = client.get_json("/authors", params=params)
    return data.get("results") or []


def get_author(
    author_id: str,
    *,
    client: OpenAlexClient,
    select: str = AUTHOR_META_SELECT,
) -> Dict[str, Any]:
    short_id = to_short_openalex_id(author_id) or author_id
    params = {"select": select} if select else None
    return client.get_json(f"/authors/{short_id}", params=params)


def list_author_works(
    author_id: str,
    *,
    client: OpenAlexClient,
    per_page: int = 20,
    sort: str = DEFAULT_AUTHOR_WORKS_SORT,
    select: str = AUTHOR_TOP_WORKS_SELECT,
) -> List[Dict[str, Any]]:
    short_id = to_short_openalex_id(author_id) or author_id
    params: Dict[str, Any] = {
        "filter": f"authorships.author.id:{short_id}",
        "per-page": per_page,
    }
    if select:
        params["select"] = select
    if sort:
        params["sort"] = sort
    data = client.get_json("/works", params=params)
    return data.get("results") or []


def get_authors_by_openalex_ids(
    author_ids: List[str],
    *,
    client: OpenAlexClient,
    select: str = AUTHOR_METRICS_SELECT,
    chunk_size: int = 50,
) -> Dict[str, Dict[str, Any]]:
    """Bulk fetch authors via `filter=openalex_id:A1|A2|...` (chunked)."""
    out: Dict[str, Dict[str, Any]] = {}
    ids = [to_short_openalex_id(x) for x in author_ids]
    ids = [x for x in ids if x]
    for i in range(0, len(ids), max(1, chunk_size)):
        chunk = ids[i : i + chunk_size]
        params: Dict[str, Any] = {
            "filter": "openalex_id:" + "|".join(chunk),
            "per-page": min(len(chunk), 200),
        }
        if select:
            params["select"] = select
        data = client.get_json("/authors", params=params)
        for item in data.get("results") or []:
            sid = to_short_openalex_id(item.get("id"))
            if sid:
                out[sid] = item
    return out

