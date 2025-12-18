"""Utilities to fetch citing papers for a given title via OpenAlex (only).

This script is a thin wrapper around:
- `pcra.openalex.OpenAlexFacade` (match/meta/list)
- `pcra.pipelines.citations` (optional enrich/filter composition)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pcra.openalex import OpenAlexFacade
from pcra.pipelines.citations import enrich_authors_with_h_index


def fetch_openalex_cited_by(
    title: str,
    max_results: int = 20,
    include_author_hindex: bool = True,
    max_author_lookups: Optional[int] = None,
) -> Dict[str, Any]:
    """Search a paper by title in OpenAlex, then fetch works that cite it.

    Notes:
    - Cited-by retrieval itself does NOT fetch per-author metrics.
    - If `include_author_hindex=True`, this function bulk-fetches author metrics
      via `/authors?filter=openalex_id:...` and attaches `h_index` to authors.
    """
    facade = OpenAlexFacade()
    match_info = facade.work_match_by_title(title, top_k=3, threshold=0.0)
    match = match_info.get("match")
    if not match or not match.get("paper_id"):
        return {"match": None, "citations": []}

    citations = facade.work_cited_by(match["paper_id"], top_k=max_results)
    if include_author_hindex:
        enrich_authors_with_h_index(
            citations, client=facade.client, max_authors=max_author_lookups
        )

    return {"match": match, "citations": citations}


if __name__ == "__main__":
    sample_title = os.environ.get("OPENALEX_SAMPLE_TITLE", "Transformers over directed acyclic graphs")
    print(f"OpenAlex citing papers for: {sample_title}")
    oa_result = fetch_openalex_cited_by(sample_title, max_results=3)
    match = oa_result.get("match") or {}
    print(f"- Matched: {match.get('paper_title')} (paper_id={match.get('paper_id')})")
    for idx, item in enumerate(oa_result.get("citations", []), 1):
        print(
            f"  [{idx}] {item.get('paper_title')} | year={item.get('year')} | authors={len(item.get('authors', []))}"
        )
