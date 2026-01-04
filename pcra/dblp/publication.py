"""DBLP publication-status lookup for cited papers."""

from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pcra.core.types import PublicationStatus


DBLP_PUBL_SEARCH_API = "https://dblp.org/search/publ/api"

PEER_REVIEWED_TYPES = {
    "Journal Articles",
    "Conference and Workshop Papers",
}
INFORMAL_TYPES = {
    "Informal and Other Publications",
}
INFORMAL_VENUES = {
    "CoRR",
}


def _normalize_title(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().strip()
    text = re.sub(r"[.\s]+$", "", text)
    text = re.sub(r"[^0-9a-z]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _title_similarity(a: str, b: str) -> float:
    a_n = _normalize_title(a)
    b_n = _normalize_title(b)
    if not a_n or not b_n:
        return 0.0
    return SequenceMatcher(a=a_n, b=b_n).ratio()


def _build_search_url(query: str, hits: int, offset: int, quoted_phrase: bool) -> str:
    q = f"\"{query}\"" if quoted_phrase else query
    params = {
        "q": q,
        "format": "json",
        "h": str(hits),
        "f": str(offset),
    }
    return f"{DBLP_PUBL_SEARCH_API}?{urllib.parse.urlencode(params)}"


def _http_get_json(url: str, timeout_s: int, max_retries: int) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PaperCitedRemarkAnalysis/DBLPQuery",
            "Accept": "application/json",
        },
        method="GET",
    )
    last_err: Optional[BaseException] = None
    attempts = max(1, int(max_retries) + 1)
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
        except Exception as exc:  # network failure fallback
            last_err = exc
            if attempt < attempts - 1:
                time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"DBLP request failed after retries: {last_err}")


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _extract_ee_links(info: Dict[str, Any]) -> List[str]:
    ee = info.get("ee")
    links: List[str] = []
    for item in _as_list(ee):
        if isinstance(item, str) and item.strip():
            links.append(item.strip())
        elif isinstance(item, dict) and item.get("text"):
            links.append(str(item["text"]).strip())
    return links


def _extract_doi(info: Dict[str, Any]) -> Optional[str]:
    doi = info.get("doi")
    if isinstance(doi, str) and doi.strip():
        return doi.strip()
    for link in _extract_ee_links(info):
        if "doi.org/" in link:
            return link.split("doi.org/")[-1].strip()
    return None


@dataclass(frozen=True)
class ScoredHit:
    sim: float
    score: float
    info: Dict[str, Any]

    @property
    def title(self) -> str:
        return str(self.info.get("title") or "")

    @property
    def venue(self) -> str:
        return str(self.info.get("venue") or "")

    @property
    def year(self) -> str:
        return str(self.info.get("year") or "")

    @property
    def pub_type(self) -> str:
        return str(self.info.get("type") or "")

    @property
    def dblp_url(self) -> str:
        return str(self.info.get("url") or "")


def _score_hits(query_title: str, hits: Iterable[Dict[str, Any]]) -> List[ScoredHit]:
    scored: List[ScoredHit] = []
    for hit in hits:
        info = hit.get("info") or {}
        title = str(info.get("title") or "")
        sim = _title_similarity(query_title, title)
        try:
            score = float(hit.get("@score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        scored.append(ScoredHit(sim=sim, score=score, info=info))
    return scored


def _pick_best_matches(
    scored: List[ScoredHit],
    min_sim: float,
) -> Tuple[List[ScoredHit], List[ScoredHit], List[ScoredHit]]:
    matched = [h for h in scored if h.sim >= min_sim]

    peer_reviewed: List[ScoredHit] = []
    informal: List[ScoredHit] = []
    others: List[ScoredHit] = []
    for h in matched:
        if h.pub_type in PEER_REVIEWED_TYPES and h.venue not in INFORMAL_VENUES:
            peer_reviewed.append(h)
        elif h.pub_type in INFORMAL_TYPES or h.venue in INFORMAL_VENUES:
            informal.append(h)
        else:
            others.append(h)

    def sort_key(item: ScoredHit) -> Tuple[float, float, int]:
        try:
            year = int(item.year)
        except (TypeError, ValueError):
            year = 0
        return (item.sim, item.score, year)

    peer_reviewed.sort(key=sort_key, reverse=True)
    informal.sort(key=sort_key, reverse=True)
    others.sort(key=sort_key, reverse=True)
    return peer_reviewed, informal, others


def _safe_hits_list(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits_obj = (result.get("result") or {}).get("hits") or {}
    hit_field = hits_obj.get("hit")
    if hit_field is None:
        return []
    if isinstance(hit_field, list):
        return hit_field
    if isinstance(hit_field, dict):
        return [hit_field]
    return []


def _build_publication_status(hit: ScoredHit, status: str) -> PublicationStatus:
    info = hit.info
    return {
        "status": status,
        "venue": info.get("venue"),
        "year": info.get("year"),
        "dblp_url": info.get("url"),
        "doi": _extract_doi(info),
        "similarity": hit.sim,
        "pub_type": info.get("type"),
    }


def query_publication_status(
    title: str,
    *,
    min_sim: float = 0.92,
    hits: int = 20,
    offset: int = 0,
    timeout_s: int = 20,
    max_retries: int = 2,
    quoted_phrase: bool = True,
) -> Tuple[PublicationStatus, Dict[str, Any]]:
    """Query DBLP and classify publication status for the given title."""

    started = time.time()
    url = _build_search_url(
        query=title,
        hits=max(1, int(hits)),
        offset=max(0, int(offset)),
        quoted_phrase=quoted_phrase,
    )
    meta: Dict[str, Any] = {"query_url": url, "elapsed_s": None, "error": None}

    try:
        payload = _http_get_json(url, timeout_s=int(timeout_s), max_retries=int(max_retries))
    except Exception as exc:
        meta["error"] = f"{type(exc).__name__}: {exc}"
        meta["elapsed_s"] = time.time() - started
        return {"status": "unknown"}, meta

    hits_list = _safe_hits_list(payload)
    scored = _score_hits(title, hits_list)
    peer_reviewed, informal, others = _pick_best_matches(scored, min_sim)

    status: PublicationStatus
    if peer_reviewed:
        status = _build_publication_status(peer_reviewed[0], "published")
    elif informal:
        status = _build_publication_status(informal[0], "informal")
    elif others:
        status = _build_publication_status(others[0], "unknown")
    else:
        status = {"status": "unknown"}
        meta["error"] = "no_match"

    meta["elapsed_s"] = time.time() - started
    meta["hits_total"] = len(hits_list)
    return status, meta
