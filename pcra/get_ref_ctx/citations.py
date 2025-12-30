"""In-text citation bracket matching and context extraction."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

from . import config
from .models import CitationContext


def _line_col(text: str, idx: int) -> Tuple[int, int]:
    line = text.count("\n", 0, idx) + 1
    last_nl = text.rfind("\n", 0, idx)
    col = idx + 1 if last_nl < 0 else (idx - last_nl)
    return line, col


_RANGE_RE = re.compile(r"^(\d+)\s*[–−-]\s*(\d+)$")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}[a-z]?\b")
_YEAR_SUFFIX_LIST_RE = re.compile(r"\b((19|20)\d{2})([a-z](?:\s*,\s*[a-z])+)\b")
_PAREN_CITATION_RE = re.compile(r"\(([^()]*\b(19|20)\d{2}[a-z]?\b[^()]*)\)")
_NARRATIVE_CITATION_RE = re.compile(
    r"\b([A-Z][A-Za-z'`-]+)"
    r"(?:\s+et\s+al\.?)?"
    r"(?:\s+(?:and|&)\s+[A-Z][A-Za-z'`-]+)?"
    r"\s*\(\s*([^)]*?\b(19|20)\d{2}[a-z]?\b[^)]*?)\s*\)",
)


def _citation_inner_includes_id(inner: str, target_id: int) -> bool:
    for part in re.split(r"[;,]", inner):
        part = part.strip()
        if not part:
            continue

        m = _RANGE_RE.match(part)
        if m:
            lo = int(m.group(1))
            hi = int(m.group(2))
            if lo <= target_id <= hi or hi <= target_id <= lo:
                return True
            continue

        if part.isdigit() and int(part) == target_id:
            return True
    return False


def extract_citation_contexts(
    body_text: str,
    ref_id: int,
    *,
    window: int,
) -> List[CitationContext]:
    """Find all in-text numeric citation brackets that include ref_id and extract contexts."""

    contexts: List[CitationContext] = []
    for m in config.CITATION_BRACKET_RE.finditer(body_text):
        inner = m.group(1)
        if not _citation_inner_includes_id(inner, ref_id):
            continue

        start, end = m.span()
        ctx_start = max(0, start - window)
        ctx_end = min(len(body_text), end + window)
        line, col = _line_col(body_text, start)

        contexts.append(
            CitationContext(
                ref_id=ref_id,
                match_text=body_text[start:end],
                start=start,
                end=end,
                line=line,
                col=col,
                context=body_text[ctx_start:ctx_end],
            )
        )
    return contexts


def _normalize_surname(text: str) -> str:
    return re.sub(r"[^a-z]", "", (text or "").lower())


def _extract_year_tokens(text: str) -> List[str]:
    tokens: List[str] = []
    seen = set()

    for m in _YEAR_SUFFIX_LIST_RE.finditer(text):
        year = m.group(1)
        suffixes = re.split(r"\s*,\s*", m.group(3))
        for suffix in suffixes:
            token = f"{year}{suffix}"
            if token not in seen:
                seen.add(token)
                tokens.append(token)

    for m in _YEAR_RE.finditer(text):
        token = m.group(0)
        if token not in seen:
            seen.add(token)
            tokens.append(token)

    return tokens


def _extract_surname_from_item(item: str) -> Optional[str]:
    cleaned = (item or "").strip()
    cleaned = re.sub(r"^(?:e\.g\.|i\.e\.|see|cf\.|see also)\s+", "", cleaned, flags=re.IGNORECASE)
    m = re.match(r"([A-Z][A-Za-z'`-]+)", cleaned)
    return m.group(1) if m else None


def _iter_author_year_items(items: Iterable[str]) -> Iterable[Tuple[str, str]]:
    for item in items:
        surname = _extract_surname_from_item(item)
        if not surname:
            continue
        surname_norm = _normalize_surname(surname)
        for year_token in _extract_year_tokens(item):
            yield surname_norm, year_token.lower()


def _append_context(
    contexts: List[CitationContext],
    body_text: str,
    start: int,
    end: int,
    *,
    ref_id: int,
    window: int,
) -> None:
    ctx_start = max(0, start - window)
    ctx_end = min(len(body_text), end + window)
    line, col = _line_col(body_text, start)
    contexts.append(
        CitationContext(
            ref_id=ref_id,
            match_text=body_text[start:end],
            start=start,
            end=end,
            line=line,
            col=col,
            context=body_text[ctx_start:ctx_end],
        )
    )


def extract_author_year_citation_contexts(
    body_text: str,
    *,
    ref_id: int,
    surname: str,
    year_with_suffix: str,
    window: int,
) -> List[CitationContext]:
    """Find all in-text author-year citations that include the target author + year."""

    target_surname = _normalize_surname(surname)
    target_year = (year_with_suffix or "").lower()
    if not target_surname or not target_year:
        return []

    contexts: List[CitationContext] = []
    seen_spans = set()

    for m in _PAREN_CITATION_RE.finditer(body_text):
        inner = m.group(1)
        items = re.split(r"\s*;\s*", inner.strip())
        matched = any(
            s == target_surname and y == target_year for s, y in _iter_author_year_items(items)
        )
        if not matched:
            continue
        start, end = m.span()
        if (start, end) in seen_spans:
            continue
        seen_spans.add((start, end))
        _append_context(contexts, body_text, start, end, ref_id=ref_id, window=window)

    for m in _NARRATIVE_CITATION_RE.finditer(body_text):
        surname = m.group(1)
        inner = m.group(2)
        years = _extract_year_tokens(inner)
        surname_norm = _normalize_surname(surname)
        if not surname_norm or not years:
            continue
        if not any(surname_norm == target_surname and y.lower() == target_year for y in years):
            continue
        start, end = m.span()
        if (start, end) in seen_spans:
            continue
        seen_spans.add((start, end))
        _append_context(contexts, body_text, start, end, ref_id=ref_id, window=window)

    return contexts
