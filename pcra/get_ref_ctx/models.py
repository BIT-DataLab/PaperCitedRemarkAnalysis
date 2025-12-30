"""Data models for reference-context extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ReferenceEntry:
    ref_id: int
    raw_text: str
    first_author: Optional[str] = None
    year: Optional[str] = None
    year_suffix: Optional[str] = None
    author_year_key: Optional[str] = None


@dataclass(frozen=True)
class CitationContext:
    ref_id: int
    match_text: str
    start: int
    end: int
    line: int
    col: int
    context: str
