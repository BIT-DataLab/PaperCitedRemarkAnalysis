"""
@todo 
下面这个脚本经过验证，能正常运行，我想给它添加一个使用openalex api-key的功能
Citation Analysis Demo using OpenAlex and Semantic Scholar APIs
================================================================

python  /data2/jproject/PaperCitedRemarkAnalysis/ref_code/chatgpt_get_citation_meta.py   "Attention is All you Need"

This Python script demonstrates how to retrieve citation information for a
scholarly work given its title. It performs two parallel tasks using the
OpenAlex and Semantic Scholar APIs:

1. **OpenAlex** – Searches for the paper by title, finds its OpenAlex ID,
   retrieves the list of papers that cite it, and then augments the result
   with detailed author metadata (including institutions and h‑index where
   available).
2. **Semantic Scholar** – Uses the paper search match endpoint to find the
   closest matching paper by title, retrieves a paginated list of citing
   papers, and enriches each author with their h‑index and affiliations.

Requirements
------------
This script only relies on the built‑in `json` module and the third‑party
`requests` library for making HTTP requests. Install `requests` with pip if
it is not already available on your system:

```
pip install requests
```

Usage Example
-------------
Run the script from the command line with a paper title. For example,
to find the citations for “The state of OA: a large‑scale analysis of the
prevalence and impact of Open Access articles”, run:

```
python citation_demo.py "The state of OA: a large‑scale analysis of the prevalence and impact of Open Access articles"
```

The script prints summaries of the citing papers for both OpenAlex and
Semantic Scholar. Because citation networks can be large, the number of
citing papers processed can be limited via the `MAX_CITATIONS` constant.
Adjust this constant to retrieve more or fewer citations.

Note on Rate Limits
-------------------
Both OpenAlex and Semantic Scholar enforce rate limits. Semantic Scholar
offers higher throughput if you obtain a free API key and supply it in the
`X-API-Key` header. Without a key the rate is limited to one request per
second. This script works without an API key for small demonstrations but
will be slow on large datasets; see the APIs' documentation for details.

References
----------
* **OpenAlex:** The official documentation explains that works are linked by
  `referenced_works` (outgoing citations) and `cited_by` (incoming
  citations).  To find works that cite a given work, filter the works
  endpoint with `cites:<work_id>`【957418439694881†L368-L391】.  Author objects
  expose `summary_stats.h_index`, which is used here to obtain h‑indices
  for each author【11693345177745†L279-L303】.
* **Semantic Scholar:** The Academic Graph API provides a paper search
  endpoint.  The `paper/search/match` endpoint returns the best match for
  a title string, and the `paper/{paperId}/citations` endpoint returns
  papers that cite the given paper, with pagination support and a
  `fields` parameter to select desired fields【801463130326079†L0-L41】.
  Author endpoints allow retrieval of names, h‑indices and affiliations【657322460333222†L644-L702】.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests

# Constants
OPENALEX_SEARCH_URL = "https://api.openalex.org/works"
OPENALEX_AUTHOR_URL = "https://api.openalex.org/authors"

SEMANTIC_SEARCH_MATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search/match"
SEMANTIC_CITATIONS_URL = "https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations"
SEMANTIC_AUTHOR_URL = "https://api.semanticscholar.org/graph/v1/author/{author_id}"

# Limit the number of citations to process to avoid excessive API calls during
# demonstration.  Set to None to fetch all citations.
MAX_CITATIONS: Optional[int] = 50


def _http_get(url: str, params: Optional[Dict[str, str]] = None,
              headers: Optional[Dict[str, str]] = None) -> Dict:
    """Helper to perform an HTTP GET request and parse the JSON response.

    Args:
        url: The URL to request.
        params: Optional dictionary of query parameters.
        headers: Optional dictionary of HTTP headers.

    Returns:
        Parsed JSON response as a Python dictionary.

    Raises:
        requests.HTTPError: If the response has an HTTP error status.
    """
    response = requests.get(url, params=params, headers=headers)
    # Raise an exception for HTTP errors (4xx, 5xx)
    response.raise_for_status()
    return response.json()


def search_openalex_work(title: str) -> Optional[str]:
    """Search for a work by title in OpenAlex and return its OpenAlex ID.

    OpenAlex supports full‑text search via the works endpoint.  To find the
    unique work ID we submit a search query and pick the first result.  You
    might refine this by comparing the returned titles to the query or by
    using additional metadata, but for demonstration purposes the top result
    usually suffices.

    Args:
        title: The title of the work to search for.

    Returns:
        The OpenAlex work ID (e.g., "W2741809807") if found; otherwise None.
    """
    params = {
        "search": title,
        "per_page": 1,  # only need the top result
    }
    data = _http_get(OPENALEX_SEARCH_URL, params=params)
    results = data.get("results", [])
    if not results:
        return None
    work_url = results[0]["id"]  # e.g., "https://openalex.org/W2741809807"
    # Extract the short ID after the last slash
    openalex_id = work_url.split("/")[-1]
    return openalex_id


def fetch_openalex_citing_works(work_id: str, max_results: Optional[int] = MAX_CITATIONS) -> List[Dict]:
    """Retrieve papers that cite the given work from OpenAlex.

    OpenAlex does not provide a direct `cited_by` list in the Work object, but
    the documentation notes that filtering the works endpoint by
    `cites:<work_id>` returns the list of works that cite the target work【957418439694881†L368-L391】.
    Because the number of citing works can be large, results are paginated
    using a cursor.  This function iterates through pages until
    `max_results` is reached or no further pages exist.

    Args:
        work_id: The OpenAlex ID of the work (e.g., "W2741809807").
        max_results: Maximum number of citing works to return; None for all.

    Returns:
        A list of citing work objects (raw API JSON entries).
    """
    citing_works: List[Dict] = []
    cursor = "*"
    # Use a large per_page to minimize the number of requests; 200 is the API max.
    per_page = 200
    while True:
        params = {
            "filter": f"cites:{work_id}",
            "per_page": per_page,
            "cursor": cursor,
        }
        data = _http_get(OPENALEX_SEARCH_URL, params=params)
        results = data.get("results", [])
        citing_works.extend(results)
        # Stop if we've reached the maximum desired citations
        if max_results is not None and len(citing_works) >= max_results:
            citing_works = citing_works[:max_results]
            break
        # Determine whether another page exists
        meta = data.get("meta", {})
        next_cursor = meta.get("next_cursor")
        if not next_cursor:
            break
        cursor = next_cursor
        # Sleep briefly to respect API rate limits (optional but polite)
        time.sleep(0.2)
    return citing_works


def fetch_openalex_author_details(author_id: str) -> Dict[str, Optional[str]]:
    """Retrieve author details from OpenAlex.

    The OpenAlex author endpoint returns detailed metadata, including summary
    statistics such as the h‑index and last known institution.  For full
    details see the OpenAlex Author documentation【11693345177745†L279-L303】.

    Args:
        author_id: The OpenAlex author ID (A‑prefixed string without the URL).

    Returns:
        A dictionary with keys: `name`, `h_index` and `institution`.  Some
        values may be None if not available.
    """
    url = f"{OPENALEX_AUTHOR_URL}/{author_id}"
    data = _http_get(url)
    # Extract author name
    name = data.get("display_name")
    # Extract h‑index from summary_stats if present
    summary_stats = data.get("summary_stats", {})
    h_index = summary_stats.get("h_index")
    # Extract the author's last known institution name (if available)
    last_institution = data.get("last_known_institution") or {}
    institution_name = last_institution.get("display_name")
    return {
        "name": name,
        "h_index": h_index,
        "institution": institution_name,
    }


def process_openalex_citations(title: str) -> List[Dict]:
    """High‑level helper to search for a work by title and process its citations in OpenAlex.

    Args:
        title: The title of the work.

    Returns:
        A list of dictionaries describing citing papers.  Each dictionary
        contains the paper title and a list of author dictionaries with
        name, institution and h‑index.
    """
    work_id = search_openalex_work(title)
    if not work_id:
        print(f"[OpenAlex] No matching work found for title: {title}")
        return []
    print(f"[OpenAlex] Found work ID: {work_id}")
    citing_works = fetch_openalex_citing_works(work_id)
    results: List[Dict] = []
    # Cache author details to avoid redundant API calls
    author_cache: Dict[str, Dict[str, Optional[str]]] = {}
    for work in citing_works:
        paper_title = work.get("display_name") or work.get("title")
        authorships = work.get("authorships", [])
        authors_list: List[Dict] = []
        for auth in authorships:
            author = auth.get("author", {})
            author_url = author.get("id")
            if not author_url:
                continue
            author_id = author_url.split("/")[-1]
            # Check cache first
            if author_id not in author_cache:
                try:
                    details = fetch_openalex_author_details(author_id)
                except requests.HTTPError:
                    # In case of HTTP errors, store minimal info
                    details = {
                        "name": author.get("display_name"),
                        "h_index": None,
                        "institution": None,
                    }
                author_cache[author_id] = details
            details = author_cache[author_id]
            authors_list.append(details)
        results.append({
            "title": paper_title,
            "authors": authors_list,
        })
    return results


def search_semantic_paper(title: str) -> Optional[str]:
    """Search for a paper by title in Semantic Scholar and return its paperId.

    The `paper/search/match` endpoint returns the paper that best matches
    the given query.  We extract the first paperId from the response.

    Args:
        title: Paper title to search for.

    Returns:
        Semantic Scholar paperId string if found; otherwise None.
    """
    params = {
        "query": title,
        "fields": "paperId,title",
    }
    data = _http_get(SEMANTIC_SEARCH_MATCH_URL, params=params)
    candidates = data.get("data", [])
    if not candidates:
        return None
    return candidates[0].get("paperId")


def fetch_semantic_citing_papers(paper_id: str, max_results: Optional[int] = MAX_CITATIONS,
                                api_key: Optional[str] = None) -> List[Dict]:
    """Retrieve papers that cite the given paper from Semantic Scholar.

    This function calls the `paper/{paper_id}/citations` endpoint, which
    returns citing papers in a paginated format.  Each entry in the `data`
    array includes a `citingPaper` object with its `paperId`, `title` and
    `authors` list【801463130326079†L0-L41】.  Pagination is handled via the
    `offset` parameter.

    Args:
        paper_id: The Semantic Scholar paperId string.
        max_results: Maximum number of citing papers to fetch; None for all.
        api_key: Optional API key to increase rate limits.

    Returns:
        A list of citing paper objects from the API.
    """
    citing_papers: List[Dict] = []
    offset = 0
    limit = 100  # maximum allowed per request
    headers = {"x-api-key": api_key} if api_key else None
    while True:
        params = {
            "fields": "title,authors",
            "limit": limit,
            "offset": offset,
        }
        url = SEMANTIC_CITATIONS_URL.format(paper_id=paper_id)
        data = _http_get(url, params=params, headers=headers)
        # Each item in data["data"] has a citingPaper
        for item in data.get("data", []):
            citing_paper = item.get("citingPaper", {})
            citing_papers.append(citing_paper)
        if max_results is not None and len(citing_papers) >= max_results:
            citing_papers = citing_papers[:max_results]
            break
        # Semantic Scholar returns a `next` string token when more pages exist.
        # However, the Graph API also supports offset based pagination.  If the
        # length of returned data is less than limit, we've reached the end.
        if len(data.get("data", [])) < limit:
            break
        offset += limit
        # Sleep to avoid hitting rate limit if no API key is provided
        if not api_key:
            time.sleep(1.1)  # abide by 1 request/s limit
    return citing_papers


def fetch_semantic_author_details(author_id: str, api_key: Optional[str] = None) -> Dict[str, Optional[str]]:
    """Retrieve author details from Semantic Scholar.

    The author endpoint returns metadata such as name, hIndex, and affiliations
    when requested via the `fields` parameter【657322460333222†L644-L702】.

    Args:
        author_id: Semantic Scholar authorId string.
        api_key: Optional API key for higher rate limits.

    Returns:
        A dictionary with keys: `name`, `h_index`, and `affiliations`.  If
        an author has no recorded affiliations, the value will be None or an
        empty list.
    """
    url = SEMANTIC_AUTHOR_URL.format(author_id=author_id)
    params = {
        "fields": "name,hIndex,affiliations",
    }
    headers = {"x-api-key": api_key} if api_key else None
    data = _http_get(url, params=params, headers=headers)
    return {
        "name": data.get("name"),
        "h_index": data.get("hIndex"),
        # Some authors have multiple affiliations; preserve the list
        "affiliations": data.get("affiliations"),
    }


def process_semantic_citations(title: str, api_key: Optional[str] = None) -> List[Dict]:
    """High‑level helper to search for a paper by title and process its citations using Semantic Scholar.

    Args:
        title: Title of the target paper.
        api_key: Optional Semantic Scholar API key for higher throughput.

    Returns:
        A list of dictionaries describing citing papers.  Each dictionary
        contains the paper title and a list of author dictionaries with
        name, h‑index and affiliations.
    """
    paper_id = search_semantic_paper(title)
    if not paper_id:
        print(f"[Semantic Scholar] No matching paper found for title: {title}")
        return []
    print(f"[Semantic Scholar] Found paper ID: {paper_id}")
    citing_papers = fetch_semantic_citing_papers(paper_id, api_key=api_key)
    results: List[Dict] = []
    # Cache to avoid repeated author lookups
    author_cache: Dict[str, Dict[str, Optional[str]]] = {}
    for paper in citing_papers:
        paper_title = paper.get("title")
        authors = paper.get("authors", [])
        paper_authors: List[Dict] = []
        for author in authors:
            author_id = author.get("authorId")
            if not author_id:
                continue
            if author_id not in author_cache:
                try:
                    details = fetch_semantic_author_details(author_id, api_key=api_key)
                except requests.HTTPError:
                    details = {
                        "name": author.get("name"),
                        "h_index": None,
                        "affiliations": None,
                    }
                author_cache[author_id] = details
            paper_authors.append(author_cache[author_id])
        results.append({
            "title": paper_title,
            "authors": paper_authors,
        })
    return results


def main():
    """Entry point when running this script from the command line."""
    if len(sys.argv) < 2:
        print("Usage: python citation_demo.py \"<paper title>\"")
        sys.exit(1)
    title = sys.argv[1]
    # Optional: read an API key from environment variable or input
    api_key = None  # Replace with your Semantic Scholar API key if available

    print(f"Searching for citations to: {title}\n")
    # Process OpenAlex citations
    oa_results = process_openalex_citations(title)
    print(f"\nOpenAlex citing papers (showing {len(oa_results)} results):")
    for i, paper in enumerate(oa_results, 1):
        print(f"\n[{i}] {paper['title']}")
        for author in paper["authors"]:
            name = author.get("name")
            h_index = author.get("h_index")
            inst = author.get("institution")
            print(f"    - {name} (h-index: {h_index}, institution: {inst})")

    # Process Semantic Scholar citations
    ss_results = process_semantic_citations(title, api_key=api_key)
    print(f"\nSemantic Scholar citing papers (showing {len(ss_results)} results):")
    for i, paper in enumerate(ss_results, 1):
        print(f"\n[{i}] {paper['title']}")
        for author in paper["authors"]:
            name = author.get("name")
            h_index = author.get("h_index")
            affil = author.get("affiliations")
            affil_str = "; ".join(affil) if isinstance(affil, list) else affil
            print(f"    - {name} (h-index: {h_index}, affiliations: {affil_str})")


if __name__ == "__main__":
    main()