"""Pure matching/scoring utilities (no network, no OpenAlex coupling)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, TypeVar

T = TypeVar("T")


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


def similarity(a: str, b: str) -> float:
    """Return a similarity score in [0, 1] using a normalized SequenceMatcher ratio."""
    return SequenceMatcher(None, _normalize_text(a), _normalize_text(b)).ratio()


def pick_best(
    query: str,
    candidates: Iterable[T],
    *,
    get_text: Callable[[T], str],
) -> Tuple[Optional[T], float]:
    """Pick best candidate by `similarity(query, get_text(candidate))`."""
    best: Optional[T] = None
    best_score = 0.0
    for cand in candidates:
        score = similarity(query, get_text(cand))
        if score > best_score:
            best = cand
            best_score = score
    return best, best_score


def score_candidates(
    query: str,
    candidates: Iterable[T],
    *,
    get_text: Callable[[T], str],
) -> List[Tuple[float, T]]:
    """Return candidates sorted by descending similarity score."""
    scored: List[Tuple[float, T]] = []
    for cand in candidates:
        scored.append((similarity(query, get_text(cand)), cand))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored

