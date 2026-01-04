"""Utilities to fetch author profile data from OpenAlex.

This file remains as a CLI/demo entry and thin wrapper around
`pcra.openalex.OpenAlexFacade` (OpenAlex only).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pcra.openalex import OpenAlexFacade


def _extract_institution_from_affiliations(affiliations: Any) -> str:
    if not isinstance(affiliations, list):
        return ""
    for aff in affiliations:
        if not isinstance(aff, dict):
            continue
        inst = aff.get("institution")
        if not isinstance(inst, dict):
            continue
        name = inst.get("display_name") or inst.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return ""


def fetch_openalex_author_profile(author_id: str) -> Dict[str, Any]:
    """Return OpenAlex Author metadata plus a few convenience top-level keys."""
    facade = OpenAlexFacade()
    info = facade.author_meta(author_id)
    data = info.get("meta") or {}

    summary_stats = data.get("summary_stats") or {}
    affiliations = data.get("affiliations")
    institution = _extract_institution_from_affiliations(affiliations)

    profile: Dict[str, Any] = {
        # Convenience / backward compatible keys
        "openalex_id": info.get("author_id"),
        "name": data.get("display_name"),
        "h_index": info.get("h_index"),
        "institution": institution or None,
        "orcid": data.get("orcid") or (data.get("ids") or {}).get("orcid"),
        # Raw (selected) OpenAlex Author object fields
        "id": data.get("id"),
        "display_name": data.get("display_name"),
        "works_count": data.get("works_count"),
        "cited_by_count": data.get("cited_by_count"),
        "summary_stats": summary_stats,
        "counts_by_year": data.get("counts_by_year"),
        "affiliations": affiliations,
        "ids": data.get("ids"),
    }
    return profile


def fetch_openalex_author_h_index(author_id: str) -> Dict[str, Any]:
    """Backward compatible alias for `fetch_openalex_author_profile`."""
    return fetch_openalex_author_profile(author_id)


if __name__ == "__main__":
    sample_openalex_id = os.environ.get("OPENALEX_SAMPLE_AUTHOR_ID", "A5112456378")  # Andrew Y. Ng
    print(f"OpenAlex author profile for {sample_openalex_id}")
    oa_profile = fetch_openalex_author_profile(sample_openalex_id)
    print(f"- {oa_profile.get('name')} | h-index={oa_profile.get('h_index')} | institution={oa_profile.get('institution')}")
    print("\nAuthor data:")
    print(json.dumps(oa_profile, ensure_ascii=False, indent=2, sort_keys=True))
