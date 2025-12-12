"""Utilities to fetch author profile data from OpenAlex or Semantic Scholar."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import requests

OA_BASE = "https://api.openalex.org"
S2_BASE = "https://api.semanticscholar.org/graph/v1"
OA_MAILTO = os.environ.get("OPENALEX_MAILTO", "1165324684@qq.com")


def _http_get_json(url: str, *, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict:
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


def fetch_openalex_author_profile(author_id: str) -> Dict[str, Any]:
    """Return the full OpenAlex Author object for an author id.

    OpenAlex Author fields (per official docs) include identifiers, names,
    works/citation metrics, affiliations & institutions, topics/concepts,
    and bookkeeping metadata. This function keeps the raw structure while
    adding a few convenience top-level keys for backward compatibility.
    """
    data = _http_get_json(f"{OA_BASE}/authors/{author_id}", params=_with_mailto(None))

    summary_stats = data.get("summary_stats") or {}
    last_known_institutions = data.get("last_known_institutions") or []
    last_institution = last_known_institutions[0] if last_known_institutions else {}

    profile: Dict[str, Any] = {
        # Convenience / backward compatible keys
        "openalex_id": author_id,
        "name": data.get("display_name"),
        "h_index": summary_stats.get("h_index"),
        "institution": last_institution.get("display_name"),
        "orcid": data.get("orcid") or (data.get("ids") or {}).get("orcid"),

        # Raw OpenAlex Author object fields
        "id": data.get("id"),
        "display_name": data.get("display_name"),
        "display_name_alternatives": data.get("display_name_alternatives"),
        "works_count": data.get("works_count"),
        "cited_by_count": data.get("cited_by_count"),
        "summary_stats": summary_stats,
        "counts_by_year": data.get("counts_by_year"),
        "affiliations": data.get("affiliations"),
        "last_known_institutions": last_known_institutions,
        "ids": data.get("ids"),
        "works_api_url": data.get("works_api_url"),
        "created_date": data.get("created_date"),
        "updated_date": data.get("updated_date"),
        "x_concepts": data.get("x_concepts"),
        "topics": data.get("topics"),
        "topic_share": data.get("topic_share"),
        "longest_name": data.get("longest_name"),
        "parsed_longest_name": data.get("parsed_longest_name"),
        "block_key": data.get("block_key"),
    }

    return profile


def fetch_openalex_author_h_index(author_id: str) -> Dict[str, Any]:
    """Backward compatible alias for `fetch_openalex_author_profile`."""
    return fetch_openalex_author_profile(author_id)


def fetch_semanticscholar_author_h_index(author_id: str, api_key: Optional[str] = None) -> Dict[str, Optional[str]]:
    """Return name, h-index and affiliations for a Semantic Scholar author id."""
    api_key = api_key or os.environ.get("S2_API_KEY")
    headers = {"User-Agent": "paper-citation-tools/0.1"}
    if api_key:
        headers["x-api-key"] = api_key
    params = {"fields": "name,hIndex,affiliations,url"}
    data = _http_get_json(f"{S2_BASE}/author/{author_id}", params=params, headers=headers)
    return {
        "name": data.get("name"),
        "h_index": data.get("hIndex"),
        "affiliations": data.get("affiliations"),
        "url": data.get("url"),
        "semantic_scholar_id": author_id,
    }


if __name__ == "__main__":
    sample_openalex_id = "A5112456378"  # Andrew Y. Ng
    print(f"OpenAlex author profile for {sample_openalex_id}")
    oa_profile = fetch_openalex_author_profile(sample_openalex_id)
    print(f"- {oa_profile.get('name')} | h-index={oa_profile.get('h_index')} | institution={oa_profile.get('institution')}")
    print("\nFull OpenAlex author data:")
    print(json.dumps(oa_profile, ensure_ascii=False, indent=2, sort_keys=True))

    api_key = os.environ.get("S2_API_KEY")
    if api_key:
        sample_s2_id = os.environ.get("S2_SAMPLE_AUTHOR_ID", "1741101")
        print(f"\nSemantic Scholar author profile for {sample_s2_id}")
        ss_profile = fetch_semanticscholar_author_h_index(sample_s2_id, api_key=api_key)
        print(f"- {ss_profile.get('name')} | h-index={ss_profile.get('h_index')} | affiliations={ss_profile.get('affiliations')}")
        print("\nFull Semantic Scholar author data:")
        print(json.dumps(ss_profile, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("\nSkip Semantic Scholar demo (set S2_API_KEY to enable).")
