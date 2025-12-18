"""Fetch full OpenAlex Work information by paper title.

This CLI tool is a thin wrapper around `pcra.openalex.OpenAlexFacade`.
It composes two top-level APIs:
  1) title -> paper_id (+ optional metadata)
  2) paper_id -> work metadata

python smoke_test/paper_info_lookup.py  "Transformers over Directed Acyclic Graphs"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pcra.openalex import OpenAlexFacade


def fetch_openalex_work_full_info_by_title(
    title: str,
    *,
    search_limit: int = 5,
    match_threshold: float = 0.6,
    include_candidates: bool = False,
) -> Dict[str, Any]:
    """Search a Work by title and return its full OpenAlex Work object.

    Returns:
        A dict with:
          - query: input title
          - match: best candidate (normalized) or None
          - match_score: similarity score in [0,1]
          - work: full Work object (raw OpenAlex response) or None
          - candidates: optional list of normalized candidates
    """
    facade = OpenAlexFacade()
    match_info = facade.work_match_by_title(
        title, top_k=search_limit, threshold=match_threshold
    )
    match = match_info.get("match")
    score = float(match_info.get("match_score") or 0.0)
    if not match:
        return {"query": title, "match": None, "match_score": score, "work": None, "candidates": []}

    paper_id = match.get("paper_id")
    if not paper_id:
        payload: Dict[str, Any] = {"query": title, "match": match, "match_score": score, "work": None}
        if include_candidates:
            payload["candidates"] = match_info.get("candidates") or []
        return payload

    work_info = facade.work_meta(paper_id, decode_abstract=True)
    full_work = dict(work_info.get("meta") or {})
    if work_info.get("abstract"):
        full_work.setdefault("abstract", work_info["abstract"])

    payload = {"query": title, "match": match, "match_score": score, "work": full_work}
    if include_candidates:
        payload["candidates"] = match_info.get("candidates") or []
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
        help="Include normalized search candidates in output.",
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
