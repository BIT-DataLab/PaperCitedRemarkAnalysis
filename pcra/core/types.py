"""Shared data structures for the refactored pipeline."""

from __future__ import annotations

from typing import List, Optional, TypedDict


class PublicationStatus(TypedDict, total=False):
    status: str
    venue: Optional[str]
    year: Optional[str]
    dblp_url: Optional[str]
    doi: Optional[str]
    similarity: Optional[float]
    pub_type: Optional[str]


class FellowStatus(TypedDict, total=False):
    ieee: str
    acm: str
    aaai: str


class InstitutionInfo(TypedDict, total=False):
    id: Optional[str]
    display_name: Optional[str]
    ror: Optional[str]
    country_code: Optional[str]


class AuthorInfo(TypedDict, total=False):
    author_id: Optional[str]
    name: Optional[str]
    h_index: Optional[int]
    affiliation: Optional[str]
    institutions: List[InstitutionInfo]
    last_known_institutions: List[InstitutionInfo]
    fellow_status: FellowStatus
    fellow_status_sources: List[str]


class Candidate(TypedDict, total=False):
    paper_id: Optional[str]
    paper_title: Optional[str]
    year: Optional[int]
    cited_by_count: Optional[int]
    authors: List[AuthorInfo]
    max_h_index_author: Optional[AuthorInfo]
    publication_status: PublicationStatus
    topk_authors: List[AuthorInfo]
    has_fellow_topk: bool
    selection_reason: str


class ScoredContext(TypedDict, total=False):
    paper_id: Optional[str]
    context: str
    context_window_size: int
    remark_score: Optional[int]
    reason: Optional[str]
    remark_error: Optional[str]
    max_h_index_author: Optional[AuthorInfo]
