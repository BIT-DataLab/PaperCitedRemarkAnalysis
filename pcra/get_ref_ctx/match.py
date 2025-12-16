"""Title-to-reference-entry matching utilities (pure, local)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, List, Optional

from .models import ReferenceEntry


def _normalize_for_match(text: str) -> str:
    """Lowercase + remove non-alnum (ASCII) for robust title matching."""

    lowered = (text or "").lower()
    lowered = lowered.replace("\u00a0", " ")  # nbsp
    lowered = re.sub(r"[^0-9a-z]+", " ", lowered)
    return " ".join(lowered.split())


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[0-9a-z]+", _normalize_for_match(text))


def _title_match_score(title: str, entry_text: str) -> float:
    """Score how well a title matches a reference entry (0..1)."""

    title_norm = _normalize_for_match(title)
    entry_norm = _normalize_for_match(entry_text)
    if not title_norm:
        return 0.0
    if title_norm in entry_norm:
        return 1.0

    title_tokens = set(_tokenize(title_norm))
    entry_tokens = set(_tokenize(entry_norm))
    if not title_tokens:
        return 0.0

    token_recall = len(title_tokens & entry_tokens) / len(title_tokens)
    seq = SequenceMatcher(None, title_norm, entry_norm).ratio()
    return max(token_recall, seq)


@dataclass(frozen=True)
class ReferenceMatch:
    entry: ReferenceEntry
    score: float


def find_reference_entry_by_title(
    entries: Iterable[ReferenceEntry],
    title: str,
    *,
    match_threshold: float,
) -> Optional[ReferenceMatch]:
    """Find the best matching reference entry for a given paper title."""

    best: Optional[ReferenceMatch] = None
    for e in entries:
        score = _title_match_score(title, e.raw_text)
        if best is None or score > best.score:
            best = ReferenceMatch(entry=e, score=score)

    if best is None or best.score < match_threshold:
        return None
    return best

