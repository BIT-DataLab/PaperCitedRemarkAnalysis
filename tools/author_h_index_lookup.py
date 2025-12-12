"""Utilities to fetch author h-index data from OpenAlex or Semantic Scholar."""

from __future__ import annotations

import os
from typing import Dict, Optional

import requests

OA_BASE = "https://api.openalex.org"
S2_BASE = "https://api.semanticscholar.org/graph/v1"


def _http_get_json(url: str, *, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict:
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Request failed {resp.status_code} for {resp.url}: {resp.text[:200]}")
    return resp.json()


def fetch_openalex_author_h_index(author_id: str) -> Dict[str, Optional[str]]:
    """Return display name, h-index and institution for an OpenAlex author id."""
    data = _http_get_json(f"{OA_BASE}/authors/{author_id}")
    summary_stats = data.get("summary_stats") or {}
    last_institution = data.get("last_known_institution") or {}
    return {
        "name": data.get("display_name"),
        "h_index": data.get("h_index") or summary_stats.get("h_index"),
        "institution": last_institution.get("display_name"),
        "orcid": data.get("orcid"),
        "openalex_id": author_id,
    }


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
    oa_profile = fetch_openalex_author_h_index(sample_openalex_id)
    print(f"- {oa_profile.get('name')} | h-index={oa_profile.get('h_index')} | institution={oa_profile.get('institution')}")

    api_key = os.environ.get("S2_API_KEY")
    if 1:
        sample_s2_id = os.environ.get("S2_SAMPLE_AUTHOR_ID", "1741101")
        print(f"\nSemantic Scholar author profile for {sample_s2_id}")
        ss_profile = fetch_semanticscholar_author_h_index(sample_s2_id, api_key=api_key)
        print(f"- {ss_profile.get('name')} | h-index={ss_profile.get('h_index')} | affiliations={ss_profile.get('affiliations')}")
    else:
        print("\nSkip Semantic Scholar demo (set S2_API_KEY to enable).")
