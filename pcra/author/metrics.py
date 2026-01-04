"""Author metrics enrichment helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pcra.openalex import authors as authors_api
from pcra.openalex.fields import AUTHOR_METRICS_SELECT
from pcra.openalex.utils import dedupe_preserve_order, normalize_institution, to_short_openalex_id
from pcra.openalex.client import OpenAlexClient


def collect_author_ids_from_works(works: List[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    for w in works:
        for a in w.get("authors") or []:
            aid = a.get("author_id")
            if aid:
                short_id = to_short_openalex_id(aid) or aid
                ids.append(short_id)
    return dedupe_preserve_order(ids)


def _normalize_institutions(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for inst in items:
        if isinstance(inst, dict):
            norm = normalize_institution(inst)
            if norm:
                normalized.append(norm)
        elif isinstance(inst, str):
            name = inst.strip()
            if name:
                normalized.append({"display_name": name})
    return normalized


def _extract_affiliation_from_institutions(institutions: List[Dict[str, Any]]) -> Optional[str]:
    if institutions:
        inst = institutions[0] or {}
        name = inst.get("display_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def enrich_authors_with_metrics(
    works: List[Dict[str, Any]],
    *,
    client: OpenAlexClient,
    max_authors: Optional[int] = None,
    chunk_size: int = 50,
) -> List[Dict[str, Any]]:
    author_ids = collect_author_ids_from_works(works)
    if max_authors is not None:
        author_ids = author_ids[: max(0, int(max_authors))]
    if not author_ids:
        return works

    authors = authors_api.get_authors_by_openalex_ids(
        author_ids, client=client, select=AUTHOR_METRICS_SELECT, chunk_size=chunk_size
    )
    metrics_map: Dict[str, Dict[str, Any]] = {}
    for aid, a in authors.items():
        summary = a.get("summary_stats") or {}
        metrics_map[aid] = {
            "h_index": summary.get("h_index") or a.get("h_index"),
        }

    for w in works:
        for a in w.get("authors") or []:
            institutions = _normalize_institutions(a.get("institutions") or [])
            if institutions:
                a["institutions"] = institutions
            aid = a.get("author_id")
            if not aid:
                continue
            short_id = to_short_openalex_id(aid) or aid
            metric = metrics_map.get(short_id)
            if not metric:
                continue
            if metric.get("h_index") is not None:
                a["h_index"] = metric["h_index"]
            if not a.get("affiliation"):
                a["affiliation"] = _extract_affiliation_from_institutions(institutions)
    return works


def compute_max_h_index_author(authors: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    best_h = None
    for a in authors:
        h = a.get("h_index")
        if not isinstance(h, int):
            continue
        if best_h is None or h > best_h:
            best_h = h
            best = a
    if best is None:
        return None
    return {
        "author_id": best.get("author_id"),
        "name": best.get("name"),
        "h_index": best_h,
        "affiliation": best.get("affiliation"),
        "institutions": best.get("institutions"),
    }
