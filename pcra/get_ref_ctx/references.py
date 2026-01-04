"""References section detection and numbered entry parsing."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple, Union

from . import config
from .models import ReferenceEntry

_INLINE_REF_ENTRY_START_RE = re.compile(r"\.\s+\[(\d+)\]\s+")
_NUMBERED_LIST_START_RE = re.compile(
    r"^\s*(?:[-*\u2022]\s+)?(\d{1,3})[.)]\s+",
    re.MULTILINE,
)
_INLINE_NUMBERED_LIST_RE = re.compile(r"(?<!\S)(\d{1,3})[.)]\s+")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}[a-z]?\b")
_LEADING_MARKER_RE = re.compile(
    r"^\s*(?:(?:[-*\u2022]\s+)?\[\d+\]\s+|[-*\u2022]\s+|\d+[.)]\s+)"
)
_LIST_ITEM_START_RE = re.compile(r"^\s*(?:[-*\u2022]\s+|\d+[.)]\s+)", re.MULTILINE)


def split_body_and_references(md_text: str) -> Tuple[str, str]:
    """Split text into (body_text, references_text) by the last References/Bibliography heading.

    Raises:
        ValueError: when no standalone References/Bibliography heading is found.
    """

    matches = list(config.REFERENCES_HEADING_RE.finditer(md_text))
    if not matches:
        raise ValueError(
            'References/Bibliography heading not found (expected a standalone line like '
            '"References", "**References**", "## References", "## **References**", "Bibliography", ...).'
        )

    m = matches[-1]
    body = md_text[: m.start()]
    references = md_text[m.end() :]
    return body, references


def _strip_leading_markers(text: str) -> str:
    return _LEADING_MARKER_RE.sub("", text or "", count=1).strip()


def _extract_author_year_fields(raw_text: str) -> Dict[str, Any]:
    cleaned = _strip_leading_markers(raw_text)

    first_author: Optional[str] = None
    m = re.match(r"([A-Z][A-Za-z'`-]+)", cleaned)
    if m:
        first_author = m.group(1)

    year: Optional[str] = None
    year_suffix: Optional[str] = None
    m = _YEAR_RE.search(cleaned)
    if m:
        year_token = m.group(0)
        year = year_token[:4]
        suffix = year_token[4:] if len(year_token) > 4 else ""
        year_suffix = suffix.lower() or None

    author_year_key: Optional[str] = None
    if first_author and year:
        year_with_suffix = year + (year_suffix or "")
        author_year_key = f"{first_author.lower()}|{year_with_suffix.lower()}"

    return {
        "first_author": first_author,
        "year": year,
        "year_suffix": year_suffix,
        "author_year_key": author_year_key,
    }


def _build_entry(ref_id: int, raw_text: str) -> ReferenceEntry:
    meta = _extract_author_year_fields(raw_text)
    return ReferenceEntry(ref_id=ref_id, raw_text=raw_text, **meta)


def _slice_entries_by_markers(
    references_text: str,
    markers: List[Tuple[int, int]],
) -> List[ReferenceEntry]:
    entries: List[ReferenceEntry] = []
    for i, (start, ref_id) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(references_text)
        raw = references_text[start:end].strip()
        if raw:
            entries.append(_build_entry(ref_id, raw))
    return entries


def _slice_entries_by_starts(references_text: str, starts: List[int]) -> List[ReferenceEntry]:
    entries: List[ReferenceEntry] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(references_text)
        raw = references_text[start:end].strip()
        if raw:
            entries.append(_build_entry(i + 1, raw))
    return entries


def _split_by_blank_lines(references_text: str) -> List[str]:
    segments = [seg.strip() for seg in re.split(r"\n\s*\n+", references_text) if seg.strip()]
    if not segments:
        return []

    merged: List[str] = []
    i = 0
    while i < len(segments):
        seg = segments[i]
        if len(seg) < 20 and i + 1 < len(segments):
            segments[i + 1] = f"{seg}\n{segments[i + 1]}"
        else:
            merged.append(seg)
        i += 1
    return merged


def _looks_like_entry_start(line: str) -> bool:
    stripped = line.lstrip()
    if not stripped:
        return False
    if _LEADING_MARKER_RE.match(stripped):
        return True
    first = stripped[0]
    return first.isalpha() and first.isupper()


def _find_year_anchor_starts(references_text: str) -> List[int]:
    starts: List[int] = []
    for m in re.finditer(r"^.*$", references_text, re.MULTILINE):
        line = m.group(0)
        if not _YEAR_RE.search(line):
            continue
        if _looks_like_entry_start(line):
            starts.append(m.start())
    return starts


def _find_list_item_starts(references_text: str) -> List[int]:
    return [m.start() for m in _LIST_ITEM_START_RE.finditer(references_text)]


def _find_numbered_list_markers(references_text: str) -> List[Tuple[int, int]]:
    markers: List[Tuple[int, int]] = []
    for m in _NUMBERED_LIST_START_RE.finditer(references_text):
        markers.append((m.start(), int(m.group(1))))

    if not markers:
        return markers

    offset = 0
    for line in references_text.splitlines(keepends=True):
        if not _NUMBERED_LIST_START_RE.match(line):
            offset += len(line)
            continue
        for m in _INLINE_NUMBERED_LIST_RE.finditer(line):
            markers.append((offset + m.start(), int(m.group(1))))
        offset += len(line)
    return markers


def parse_reference_entries(
    references_text: str,
    *,
    return_meta: bool = False,
) -> Union[List[ReferenceEntry], Tuple[List[ReferenceEntry], Dict[str, Any]]]:
    """Parse reference entries from the References section text.

    When no numeric "[id]" markers exist, fall back to heuristic splitting.
    """

    meta: Dict[str, Any] = {"method": None, "has_numeric_ids": False}

    start_markers: List[Tuple[int, int]] = []
    used_numbered_list = False
    for m in config.REF_ENTRY_START_RE.finditer(references_text):
        start_markers.append((m.start(), int(m.group(1))))
    for m in _INLINE_REF_ENTRY_START_RE.finditer(references_text):
        # group(1) captures digits; the `[` is right before it.
        start_markers.append((m.start(1) - 1, int(m.group(1))))
    if not start_markers:
        list_markers = _find_numbered_list_markers(references_text)
        if list_markers:
            start_markers.extend(list_markers)
            used_numbered_list = True

    if start_markers:
        start_markers.sort(key=lambda x: x[0])
        dedup: List[Tuple[int, int]] = []
        seen_pos = set()
        for pos, rid in start_markers:
            if pos in seen_pos:
                continue
            seen_pos.add(pos)
            dedup.append((pos, rid))
        method = "numeric_list" if used_numbered_list else "numeric"
        meta.update({"method": method, "has_numeric_ids": True})
        entries = _slice_entries_by_markers(references_text, dedup)
        return (entries, meta) if return_meta else entries

    entries_text = _split_by_blank_lines(references_text)
    if len(entries_text) >= 2:
        meta.update({"method": "blank_lines", "has_numeric_ids": False})
        entries = [_build_entry(i + 1, raw) for i, raw in enumerate(entries_text)]
        return (entries, meta) if return_meta else entries

    year_starts = _find_year_anchor_starts(references_text)
    if year_starts:
        year_starts = sorted(set(year_starts))
        if year_starts[0] != 0 and references_text[: year_starts[0]].strip():
            year_starts = [0] + year_starts
        if len(year_starts) >= 1:
            meta.update({"method": "year_anchors", "has_numeric_ids": False})
            entries = _slice_entries_by_starts(references_text, year_starts)
            return (entries, meta) if return_meta else entries

    list_starts = _find_list_item_starts(references_text)
    if list_starts:
        list_starts = sorted(set(list_starts))
        if list_starts[0] != 0 and references_text[: list_starts[0]].strip():
            list_starts = [0] + list_starts
        meta.update({"method": "list_items", "has_numeric_ids": False})
        entries = _slice_entries_by_starts(references_text, list_starts)
        return (entries, meta) if return_meta else entries

    cleaned = references_text.strip()
    if cleaned:
        meta.update({"method": "single_entry", "has_numeric_ids": False})
        entries = [_build_entry(1, cleaned)]
        return (entries, meta) if return_meta else entries

    meta.update({"method": "empty", "has_numeric_ids": False})
    entries = []
    return (entries, meta) if return_meta else entries
