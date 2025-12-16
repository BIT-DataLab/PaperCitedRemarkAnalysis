"""References section detection and numbered entry parsing."""

from __future__ import annotations

from typing import List, Tuple

from . import config
from .models import ReferenceEntry


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

    starts = list(config.REF_ENTRY_START_RE.finditer(references_text))
    if not starts:
        return []

    entries: List[ReferenceEntry] = []
    for i, m in enumerate(starts):
        ref_id = int(m.group(1))
        start = m.start()
        end = starts[i + 1].start() if i + 1 < len(starts) else len(references_text)
        raw = references_text[start:end].strip()
        entries.append(ReferenceEntry(ref_id=ref_id, raw_text=raw))
    return entries

