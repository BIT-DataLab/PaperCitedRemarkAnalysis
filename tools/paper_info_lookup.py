"""Fetch full OpenAlex Work information by paper title.

This module mirrors the style of other lookup utilities in `tools/`.
Given a paper title, it searches OpenAlex Works and retrieves the full
Work object for the best matching result.

OpenAlex Works search endpoint:
  GET https://api.openalex.org/works?search=<title>&per-page=N
Single Work endpoint:
  GET https://api.openalex.org/works/{id}
"""

from __future__ import annotations

import argparse
import json
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import requests

OA_BASE = "https://api.openalex.org"
OA_MAILTO = os.environ.get("OPENALEX_MAILTO", "1165324684@qq.com")
USER_AGENT = os.environ.get("OPENALEX_USER_AGENT", "paper-info-lookup/0.1")


def _http_get_json(url: str, *, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict:
    headers = headers.copy() if headers else {}
    headers.setdefault("User-Agent", USER_AGENT)
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Request failed {resp.status_code} for {resp.url}: {resp.text[:200]}")
    return resp.json()


def _with_mailto(params: Optional[Dict]) -> Dict:
    """Attach mailto for OpenAlex polite pool if configured."""
    params = params.copy() if params else {}
    if OA_MAILTO:
        params.setdefault("mailto", OA_MAILTO)
    return params


def _normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"[^\w\s]", "", title)
    return title.strip()


def _title_similarity(query: str, candidate: str) -> float:
    return SequenceMatcher(None, _normalize_title(query), _normalize_title(candidate)).ratio()


def search_openalex_works_by_title(title: str, *, limit: int = 5) -> List[Dict[str, Any]]:
    """Return a list of Work search candidates for a title."""
    params = {"search": title, "per-page": limit}
    data = _http_get_json(f"{OA_BASE}/works", params=_with_mailto(params))
    return data.get("results") or []


def pick_best_work_by_title(
    title: str,
    candidates: List[Dict[str, Any]],
    *,
    threshold: float = 0.6,
) -> Tuple[Optional[Dict[str, Any]], float]:
    """Pick best matching Work from candidates using simple title similarity."""
    if not candidates:
        return None, 0.0
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for cand in candidates:
        cand_title = cand.get("display_name") or cand.get("title") or ""
        scored.append((_title_similarity(title, cand_title), cand))
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    if best_score < threshold:
        # Still return the best candidate, but caller may treat as low confidence.
        return best, best_score
    return best, best_score


def fetch_openalex_work_full_info_by_title(
    title: str,
    *,
    search_limit: int = 5,
    match_threshold: float = 0.6,
    include_candidates: bool = False,
) -> Dict[str, Any]:
    """Search a Work by title and return its full OpenAlex Work object.

    Args:
        title: Paper title to search.
        search_limit: Number of search candidates to consider.
        match_threshold: Similarity threshold for "confident" match.
        include_candidates: Whether to include search candidates in return.

    Returns:
        A dict with:
          - query: input title
          - match: best candidate (dehydrated) or None
          - match_score: similarity score in [0,1]
          - work: full Work object (raw OpenAlex response) or None
          - candidates: optional list of dehydrated candidates
    """
    candidates = search_openalex_works_by_title(title, limit=search_limit)
    best, score = pick_best_work_by_title(title, candidates, threshold=match_threshold)
    if not best:
        return {"query": title, "match": None, "match_score": score, "work": None, "candidates": []}

    best_id = best.get("id")
    if not best_id:
        payload = {"query": title, "match": best, "match_score": score, "work": None}
        if include_candidates:
            payload["candidates"] = candidates
        return payload

    work_short_id = best_id.split("/")[-1]
    full_work = _http_get_json(f"{OA_BASE}/works/{work_short_id}", params=_with_mailto(None))

    # Convenience: decode abstract if inverted index exists.
    abstract_inverted = full_work.get("abstract_inverted_index")
    if abstract_inverted and isinstance(abstract_inverted, dict):
        tokens = []
        for word, positions in abstract_inverted.items():
            for pos in positions:
                tokens.append((pos, word))
        tokens.sort(key=lambda x: x[0])
        full_work.setdefault("abstract", " ".join(w for _, w in tokens))

    payload: Dict[str, Any] = {
        "query": title,
        "match": best,
        "match_score": score,
        "work": full_work,
    }
    if include_candidates:
        payload["candidates"] = candidates
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Lookup full OpenAlex Work info by title.")
    parser.add_argument(
        "title",
        nargs="?",
        help="Paper title to search in OpenAlex.",
        default=os.environ.get("OPENALEX_SAMPLE_TITLE", "Attention Is All You Need"),
    )
    parser.add_argument(
        "--candidates",
        action="store_true",
        help="Include dehydrated search candidates in output.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of search results to consider.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.6,
        help="Similarity threshold for confident match.",
    )
    args = parser.parse_args()

    info = fetch_openalex_work_full_info_by_title(
        args.title,
        search_limit=args.limit,
        match_threshold=args.threshold,
        include_candidates=args.candidates,
    )
    print(json.dumps(info, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
