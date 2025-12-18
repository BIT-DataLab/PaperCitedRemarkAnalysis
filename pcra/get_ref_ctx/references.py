"""References section detection and numbered entry parsing."""

from __future__ import annotations

import re
from typing import List, Tuple

from . import config
from .models import ReferenceEntry

_INLINE_REF_ENTRY_START_RE = re.compile(r"\.\s+\[(\d+)\]\s+")


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


def parse_reference_entries(references_text: str) -> List[ReferenceEntry]:
    """Parse numbered reference entries from the References section text."""

    start_markers: List[Tuple[int, int]] = []
    for m in config.REF_ENTRY_START_RE.finditer(references_text):
        start_markers.append((m.start(), int(m.group(1))))
    for m in _INLINE_REF_ENTRY_START_RE.finditer(references_text):
        # group(1) captures digits; the `[` is right before it.
        start_markers.append((m.start(1) - 1, int(m.group(1))))

    if not start_markers:
        return []

    start_markers.sort(key=lambda x: x[0])
    dedup: List[Tuple[int, int]] = []
    seen_pos = set()
    for pos, rid in start_markers:
        if pos in seen_pos:
            continue
        seen_pos.add(pos)
        dedup.append((pos, rid))

    entries: List[ReferenceEntry] = []
    for i, (start, ref_id) in enumerate(dedup):
        end = dedup[i + 1][0] if i + 1 < len(dedup) else len(references_text)
        raw = references_text[start:end].strip()
        entries.append(ReferenceEntry(ref_id=ref_id, raw_text=raw))
    return entries
