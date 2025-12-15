"""Resolve a search result URL into a best-matching PDF URL."""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests

from . import config

logger = logging.getLogger(__name__)


def is_pdf_url(url: str) -> bool:
    return url.lower().split("?", 1)[0].endswith(".pdf")


def is_openreview_url(url: str) -> bool:
    return "openreview.net" in (urlparse(url).hostname or "")


def is_arxiv_url(url: str) -> bool:
    return "arxiv.org" in (urlparse(url).hostname or "")


def is_pdf_like_url(url: str) -> bool:
    if is_pdf_url(url):
        return True
    parsed = urlparse(url)
    path_q = (parsed.path or "") + ("?" + parsed.query if parsed.query else "")
    path_l = path_q.lower()
    if is_openreview_url(url) and parsed.path.startswith("/pdf"):
        return True
    pdf_hints = [
        "pdf?",
        "format=pdf",
        "type=pdf",
        "/download/pdf",
        "pdf-download",
        "pdf_file=",
    ]
    return any(hint in path_l for hint in pdf_hints)


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname and "duckduckgo.com" in parsed.hostname and parsed.path.startswith("/l"):
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            try:
                return unquote(qs["uddg"][0])
            except Exception:
                pass
    return url


def arxiv_to_pdf_url(url: str) -> Optional[str]:
    url = normalize_url(url)
    parsed = urlparse(url)
    if not parsed.hostname or "arxiv.org" not in parsed.hostname:
        return None

    path = parsed.path or ""
    if path.startswith("/pdf/"):
        return f"https://arxiv.org{path}" if path.lower().endswith(".pdf") else f"https://arxiv.org{path}.pdf"
    if path.startswith("/abs/"):
        paper_id = path.split("/abs/", 1)[1].strip("/")
        if paper_id:
            return f"https://arxiv.org/pdf/{paper_id}.pdf"
    return None


def get_query_tokens(query: str) -> List[str]:
    tokens = [tok for tok in re.split(r"\W+", (query or "").lower()) if tok]
    return [tok for tok in tokens if tok not in config.STOP_TOKENS and len(tok) > 2]


def token_hits(text: str, tokens: List[str]) -> int:
    text_l = (text or "").lower()
    return sum(tok in text_l for tok in tokens)


def title_score(result_title: str, query: str) -> Tuple[int, float]:
    tokens = get_query_tokens(query)
    if not tokens:
        return 0, 1.0
    hits = token_hits(result_title, tokens)
    overlap = hits / len(tokens)
    return hits, overlap


def title_is_relevant(
    result_title: str,
    query: str,
    *,
    min_hits: int = config.MIN_TITLE_HITS,
    min_overlap: float = config.MIN_TITLE_OVERLAP,
) -> bool:
    hits, overlap = title_score(result_title, query)
    return hits >= min_hits and overlap >= min_overlap


def score_match(text: str, query: str) -> int:
    tokens = get_query_tokens(query)
    if not tokens:
        return 0
    return token_hits(text, tokens)


def extract_pdf_links_from_html(html: str, base_url: str) -> List[str]:
    candidates = re.findall(r'(?:href|src)=["\']([^"\']+)["\']', html or "", flags=re.I)
    candidates += re.findall(r'content=["\']([^"\']+\.pdf)["\']', html or "", flags=re.I)

    pdfs: List[str] = []
    seen = set()
    for href in candidates:
        full = urljoin(base_url, href)
        if is_pdf_like_url(full) and full not in seen:
            seen.add(full)
            pdfs.append(full)
    return pdfs


def is_page_matching_query(
    html: str,
    query: str,
    *,
    min_hits: int = config.MIN_TITLE_HITS,
    min_overlap: float = config.MIN_TITLE_OVERLAP,
) -> bool:
    text = re.sub(r"<[^>]+>", " ", html or "")
    tokens = get_query_tokens(query)
    if not tokens:
        return False
    hits = token_hits(text, tokens)
    overlap = hits / len(tokens)
    return hits >= min_hits and overlap >= min_overlap


def find_pdf_for_result(
    *,
    title: str,
    url: str,
    query: str,
    min_pdf_score: int = config.MIN_PDF_SCORE,
) -> Optional[str]:
    url = normalize_url(url)

    if is_openreview_url(url):
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if parsed.path.startswith("/pdf"):
            return url
        if parsed.path.startswith("/forum") and "id" in qs:
            try:
                resp = requests.get(url, headers=config.DEFAULT_HEADERS, timeout=config.PAGE_FETCH_TIMEOUT_S)
                resp.raise_for_status()
            except Exception as exc:
                logger.info("OpenReview page fetch failed %s: %s", url, exc)
                return None

            if not is_page_matching_query(resp.text, query):
                logger.info("OpenReview page does not match query, skip: %s", url)
                return None

            pdf_url = f"https://openreview.net/pdf?id={qs['id'][0]}"
            logger.info("OpenReview forum -> PDF: %s", pdf_url)
            return pdf_url

    if is_arxiv_url(url):
        pdf = arxiv_to_pdf_url(url)
        if pdf:
            logger.info("arXiv -> PDF: %s", pdf)
            return pdf
        logger.info("Found arXiv url but could not parse PDF: %s", url)
        return None

    if is_pdf_url(url):
        return url

    try:
        resp = requests.get(url, headers=config.DEFAULT_HEADERS, timeout=config.PAGE_FETCH_TIMEOUT_S)
        resp.raise_for_status()
    except Exception as exc:
        logger.info("Page fetch failed %s: %s", url, exc)
        return None

    page_relevant = is_page_matching_query(resp.text, query)
    pdf_links = extract_pdf_links_from_html(resp.text, url)
    if not pdf_links:
        if page_relevant:
            logger.info("Page seems relevant but no PDF link found: %s", url)
        else:
            logger.debug("No PDF link found: %s", url)
        return None

    best: Optional[str] = None
    best_score = -1
    combined_ref = f"{title} {resp.text[:1000]}"
    for pdf_url in pdf_links:
        score = score_match(pdf_url, query)
        score = max(score, score_match(combined_ref, query))
        if score > best_score:
            best = pdf_url
            best_score = score

    if best is None:
        return None

    if best_score < min_pdf_score and not page_relevant:
        logger.info(
            "PDF score too low (score=%s) and page not relevant; skip: %s",
            best_score,
            best,
        )
        return None
    return best


def fetch_pdf_url_from_page_url(url: str, query: str) -> Optional[str]:
    norm = normalize_url(url)

    if is_openreview_url(norm):
        parsed = urlparse(norm)
        qs = parse_qs(parsed.query)
        if parsed.path.startswith("/pdf"):
            return norm
        if parsed.path.startswith("/forum") and "id" in qs:
            try:
                resp = requests.get(norm, headers=config.DEFAULT_HEADERS, timeout=config.PAGE_FETCH_TIMEOUT_S)
                resp.raise_for_status()
            except Exception as exc:
                logger.info("OpenReview page fetch failed %s: %s", norm, exc)
                return None

            if not is_page_matching_query(resp.text, query):
                logger.info("OpenReview page does not match query, skip: %s", norm)
                return None
            return f"https://openreview.net/pdf?id={qs['id'][0]}"

    if is_pdf_url(norm):
        return norm

    try:
        resp = requests.get(norm, headers=config.DEFAULT_HEADERS, timeout=config.PAGE_FETCH_TIMEOUT_S)
        resp.raise_for_status()
    except Exception as exc:
        logger.info("Page fetch failed %s: %s", norm, exc)
        return None

    page_relevant = is_page_matching_query(resp.text, query)
    pdf_links = extract_pdf_links_from_html(resp.text, norm)
    if not pdf_links:
        if page_relevant:
            logger.info("Page seems relevant but no PDF link found: %s", norm)
        return None

    best = None
    best_score = -1
    for pdf_url in pdf_links:
        score = score_match(pdf_url, query)
        if score > best_score:
            best = pdf_url
            best_score = score

    if best is None:
        return None
    if best_score < config.MIN_PDF_SCORE and not page_relevant:
        logger.info("PDF score too low (score=%s) and page not relevant; skip: %s", best_score, best)
        return None
    return best
