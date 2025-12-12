"""Utilities to fetch citing papers for a given title via OpenAlex or Semantic Scholar."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import requests

OA_BASE = "https://api.openalex.org"
S2_BASE = "https://api.semanticscholar.org/graph/v1"


def _http_get_json(url: str, *, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict:
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Request failed {resp.status_code} for {resp.url}: {resp.text[:200]}")
    return resp.json()


# --------------------------- OpenAlex path --------------------------- #
def _search_openalex_work(title: str) -> Optional[Dict]:
    params = {"filter": f"title.search:{title}", "per-page": 1}
    data = _http_get_json(f"{OA_BASE}/works", params=params)
    results = data.get("results") or []
    return results[0] if results else None


def _get_openalex_author_h_index(author_id: str, cache: Dict[str, Optional[int]]) -> Optional[int]:
    if author_id in cache:
        return cache[author_id]
    try:
        author = _http_get_json(f"{OA_BASE}/authors/{author_id}")
        cache[author_id] = author.get("h_index") or author.get("summary_stats", {}).get("h_index")
    except Exception:
        cache[author_id] = None
    return cache[author_id]


def fetch_openalex_cited_by(
    title: str,
    max_results: int = 20,
    include_author_hindex: bool = True,
    max_author_lookups: int = 30,
) -> Dict:
    """Search a paper by title in OpenAlex, then fetch works that cite it."""
    target = _search_openalex_work(title)
    if not target:
        return {"match": None, "citations": []}

    work_id = target["id"].split("/")[-1]
    params = {
        "filter": f"cites:{work_id}",
        "per-page": max_results,
        "select": "id,display_name,authorships,publication_year,doi,cited_by_count",
        "sort": "cited_by_count:desc",
    }
    data = _http_get_json(f"{OA_BASE}/works", params=params)

    author_cache: Dict[str, Optional[int]] = {}
    lookups_left = max_author_lookups
    citations: List[Dict] = []
    for item in data.get("results", []):
        authors = []
        for auth in item.get("authorships") or []:
            author_info = auth.get("author") or {}
            author_id = (author_info.get("id") or "").split("/")[-1] if author_info.get("id") else None
            h_index = None
            if include_author_hindex and author_id and lookups_left > 0:
                h_index = _get_openalex_author_h_index(author_id, author_cache)
                lookups_left -= 1

            authors.append(
                {
                    "name": author_info.get("display_name"),
                    "openalex_id": author_id,
                    "orcid": author_info.get("orcid"),
                    "h_index": h_index,
                    "institutions": [inst.get("display_name") for inst in auth.get("institutions") or []],
                }
            )

        citations.append(
            {
                "title": item.get("display_name"),
                "openalex_id": item.get("id"),
                "doi": item.get("doi"),
                "year": item.get("publication_year"),
                "authors": authors,
                "cited_by_count": item.get("cited_by_count"),
            }
        )

    return {
        "match": {
            "title": target.get("display_name"),
            "openalex_id": target.get("id"),
            "doi": target.get("doi"),
            "year": target.get("publication_year"),
            "cited_by_count": target.get("cited_by_count"),
        },
        "citations": citations,
    }


# ---------------------- Semantic Scholar path ----------------------- #
def _s2_headers(api_key: Optional[str]) -> Dict[str, str]:
    headers = {"User-Agent": "paper-citation-tools/0.1"}
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def _search_s2_paper(title: str, api_key: Optional[str]) -> Optional[Dict]:
    params = {"query": title, "limit": 1, "fields": "title,authors,year,externalIds,url"}
    data = _http_get_json(f"{S2_BASE}/paper/search", params=params, headers=_s2_headers(api_key))
    results = data.get("data") or []
    return results[0] if results else None


def fetch_semanticscholar_cited_by(
    title: str,
    *,
    api_key: Optional[str] = None,
    max_results: int = 20,
    enrich_authors: bool = True,
    max_author_lookups: int = 30,
) -> Dict:
    """Resolve a paper by title in Semantic Scholar, then pull its citing papers."""
    api_key = api_key or os.environ.get("S2_API_KEY")
    target = _search_s2_paper(title, api_key)
    if not target:
        return {"match": None, "citations": []}

    paper_id = target.get("paperId") or target.get("paper_id") or target.get("id")
    if not paper_id:
        return {"match": target, "citations": []}

    fields = ",".join(
        [
            "citingPaper.title",
            "citingPaper.url",
            "citingPaper.year",
            "citingPaper.externalIds",
            "citingPaper.authors",
        ]
    )
    params = {"fields": fields, "limit": max_results}
    data = _http_get_json(
        f"{S2_BASE}/paper/{paper_id}/citations",
        params=params,
        headers=_s2_headers(api_key),
    )

    author_cache: Dict[str, Dict] = {}
    lookups_left = max_author_lookups

    def _enrich_author(author_id: str) -> Dict:
        nonlocal lookups_left
        if author_id in author_cache:
            return author_cache[author_id]
        if not enrich_authors or lookups_left <= 0:
            author_cache[author_id] = {}
            return {}
        try:
            details = _http_get_json(
                f"{S2_BASE}/author/{author_id}",
                params={"fields": "name,affiliations,hIndex"},
                headers=_s2_headers(api_key),
            )
            author_cache[author_id] = {
                "affiliations": details.get("affiliations"),
                "h_index": details.get("hIndex"),
            }
        except Exception:
            author_cache[author_id] = {}
        lookups_left -= 1
        return author_cache[author_id]

    citations: List[Dict] = []
    for entry in data.get("data", []):
        citing = entry.get("citingPaper") or {}
        authors = []
        for author in citing.get("authors") or []:
            author_id = author.get("authorId") or author.get("author_id")
            extra = _enrich_author(author_id) if author_id else {}
            authors.append(
                {
                    "name": author.get("name"),
                    "semantic_scholar_id": author_id,
                    "affiliations": extra.get("affiliations"),
                    "h_index": extra.get("h_index"),
                }
            )
        citations.append(
            {
                "title": citing.get("title"),
                "url": citing.get("url"),
                "year": citing.get("year"),
                "externalIds": citing.get("externalIds"),
                "authors": authors,
            }
        )

    return {
        "match": {
            "title": target.get("title"),
            "paperId": paper_id,
            "year": target.get("year"),
            "externalIds": target.get("externalIds"),
            "url": target.get("url"),
        },
        "citations": citations,
    }


if __name__ == "__main__":
    sample_title = "Transformers over directed acyclic graphs"
    print(f"OpenAlex citing papers for: {sample_title}")
    oa_result = fetch_openalex_cited_by(sample_title, max_results=3)
    match = oa_result.get("match") or {}
    print(f"- Matched: {match.get('title')} (doi={match.get('doi')})")
    for idx, item in enumerate(oa_result.get("citations", []), 1):
        print(f"  [{idx}] {item.get('title')} | doi={item.get('doi')} | authors={len(item.get('authors', []))}")

    api_key = os.environ.get("S2_API_KEY")
    if 1:
        print("\nSemantic Scholar citing papers (requires S2_API_KEY):")
        s2_result = fetch_semanticscholar_cited_by(sample_title, api_key=api_key, max_results=3)
        s2_match = s2_result.get("match") or {}
        print(f"- Matched: {s2_match.get('title')} ({s2_match.get('paperId')})")
        for idx, item in enumerate(s2_result.get("citations", []), 1):
            ext_ids = item.get("externalIds") or {}
            doi = ext_ids.get("DOI") if isinstance(ext_ids, dict) else None
            print(f"  [{idx}] {item.get('title')} | doi={doi} | authors={len(item.get('authors', []))}")
    else:
        print("\nSkip Semantic Scholar demo (set S2_API_KEY to enable).")
