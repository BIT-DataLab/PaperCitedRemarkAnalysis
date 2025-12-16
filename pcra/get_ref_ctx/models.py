"""Data models for reference-context extraction."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceEntry:
    ref_id: int
    raw_text: str


@dataclass(frozen=True)
class CitationContext:
    ref_id: int
    match_text: str
    start: int
    end: int
    line: int
    col: int
    context: str

