"""OpenAlex Facade: stable top-level APIs for system integration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pcra.domain import scoring

from .client import OpenAlexClient
from .fields import (
    AUTHOR_MATCH_SELECT,
    AUTHOR_META_SELECT,
    AUTHOR_TOP_WORKS_SELECT,
    DEFAULT_AUTHOR_WORKS_SORT,
    DEFAULT_CITED_BY_SORT,
    MAX_PER_PAGE,
    WORK_CITED_BY_SELECT,
    WORK_MATCH_SELECT,
    WORK_META_SELECT,
)
from .utils import decode_abstract_inverted_index, join_fields, normalize_institution, to_short_openalex_id
from . import authors as authors_api
from . import works as works_api


class OpenAlexFacade:
    """System-facing OpenAlex APIs (match/meta/list)."""

    def __init__(self, client: Optional[OpenAlexClient] = None) -> None:
        self.client = client or OpenAlexClient()

    # ----------------------------- Work APIs ----------------------------- #
    def work_match_by_title(
        self,
        title: str,
        *,
        top_k: int = 3,
        threshold: float = 0.6,
        fields: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        select = join_fields(fields) or WORK_MATCH_SELECT
        raw_candidates = works_api.search_works_by_title(
            title, client=self.client, per_page=top_k, select=select
        )
        best_raw, best_score = scoring.pick_best(
            title, raw_candidates, get_text=lambda c: c.get("display_name") or c.get("title") or ""
        )
        candidates = [self._dehydrate_work(x) for x in raw_candidates]
        match = self._dehydrate_work(best_raw) if best_raw else None
        return {
            "query": title,
            "match": match,
            "match_score": best_score,
            "is_confident": bool(match and best_score >= threshold),
            "candidates": candidates,
        }

    def work_meta(
        self,
        paper_id: str,
        *,
        fields: Optional[Union[str, List[str]]] = None,
        decode_abstract: bool = True,
    ) -> Dict[str, Any]:
        select = join_fields(fields) or WORK_META_SELECT
        meta = works_api.get_work(paper_id, client=self.client, select=select)
        short_id = to_short_openalex_id(meta.get("id")) or to_short_openalex_id(paper_id) or paper_id
        abstract = decode_abstract_inverted_index(meta) if decode_abstract else None
        return {
            "paper_id": short_id,
            "paper_title": meta.get("display_name") or meta.get("title"),
            "paper_doi": meta.get("doi") or (meta.get("ids") or {}).get("doi"),
            "year": meta.get("publication_year"),
            "cited_by_count": meta.get("cited_by_count"),
            "abstract": abstract,
            "meta": meta,
        }

    def work_cited_by(
        self,
        paper_id: str,
        *,
        top_k: int = 20,
        fields: Optional[Union[str, List[str]]] = None,
        sort: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        select = join_fields(fields) or WORK_CITED_BY_SELECT
        raw = works_api.list_citing_works(
            paper_id,
            client=self.client,
            per_page=top_k,
            select=select,
            sort=sort or DEFAULT_CITED_BY_SORT,
        )
        return [self._dehydrate_work(x) for x in raw]

    # ---------------------------- Author APIs ---------------------------- #
    def author_match_by_name(
        self,
        name: str,
        *,
        top_k: int = 3,
        threshold: float = 0.6,
        fields: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        select = join_fields(fields) or AUTHOR_MATCH_SELECT
        raw_candidates = authors_api.search_authors_by_name(
            name, client=self.client, per_page=top_k, select=select
        )
        best_raw, best_score = scoring.pick_best(
            name, raw_candidates, get_text=lambda c: c.get("display_name") or ""
        )
        candidates = [self._dehydrate_author(x) for x in raw_candidates]
        match = self._dehydrate_author(best_raw) if best_raw else None
        return {
            "query": name,
            "match": match,
            "match_score": best_score,
            "is_confident": bool(match and best_score >= threshold),
            "candidates": candidates,
        }

    def author_meta(
        self,
        author_id: str,
        *,
        fields: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        select = join_fields(fields) or AUTHOR_META_SELECT
        meta = authors_api.get_author(author_id, client=self.client, select=select)
        short_id = to_short_openalex_id(meta.get("id")) or to_short_openalex_id(author_id) or author_id
        summary_stats = meta.get("summary_stats") or {}
        h_index = summary_stats.get("h_index") or meta.get("h_index")
        return {
            "author_id": short_id,
            "author_name": meta.get("display_name"),
            "h_index": h_index,
            "works_count": meta.get("works_count"),
            "cited_by_count": meta.get("cited_by_count"),
            "meta": meta,
        }

    def author_top_works(
        self,
        author_id: str,
        *,
        top_k: int = 20,
        sort: Optional[str] = None,
        only_first_author: bool = False,
        fields: Optional[Union[str, List[str]]] = None,
    ) -> List[Dict[str, Any]]:
        select = join_fields(fields) or AUTHOR_TOP_WORKS_SELECT
        per_page = top_k
        if only_first_author:
            per_page = min(MAX_PER_PAGE, max(top_k * 5, 50))
        raw = authors_api.list_author_works(
            author_id,
            client=self.client,
            per_page=per_page,
            sort=sort or DEFAULT_AUTHOR_WORKS_SORT,
            select=select,
        )
        works = [self._dehydrate_work(x) for x in raw]
        if not only_first_author:
            return works[:top_k]
        aid = to_short_openalex_id(author_id) or author_id

        def is_first_author(work: Dict[str, Any]) -> bool:
            for a in work.get("authors") or []:
                if a.get("author_id") == aid and a.get("author_position") == "first":
                    return True
            return False

        first_author_works = [w for w in works if is_first_author(w)]
        first_author_works.sort(
            key=lambda w: ((w.get("cited_by_count") or 0), (w.get("year") or 0)),
            reverse=True,
        )
        return first_author_works[:top_k]

    # --------------------------- Dehydrators ---------------------------- #
    @staticmethod
    def _extract_venue(work: Dict[str, Any]) -> Optional[str]:
        primary = work.get("primary_location") or {}
        source = primary.get("source") or {}
        for key in ("display_name", "name"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        host = work.get("host_venue") or {}
        for key in ("display_name", "name"):
            value = host.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        venue = work.get("venue")
        if isinstance(venue, str) and venue.strip():
            return venue.strip()
        return None

    @staticmethod
    def _dehydrate_work(work: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not work:
            return None
        id_url = work.get("id")
        paper_id = to_short_openalex_id(id_url) or to_short_openalex_id(work.get("openalex_id"))
        title = work.get("display_name") or work.get("title")
        doi = work.get("doi") or (work.get("ids") or {}).get("doi")
        venue = OpenAlexFacade._extract_venue(work)

        authors: List[Dict[str, Any]] = []
        for auth in work.get("authorships") or []:
            author = auth.get("author") or {}
            author_id = to_short_openalex_id(author.get("id"))
            institutions = [
                inst for inst in (normalize_institution(x) for x in (auth.get("institutions") or [])) if inst
            ]
            authors.append(
                {
                    "author_id": author_id,
                    "name": author.get("display_name"),
                    "orcid": author.get("orcid") or (author.get("ids") or {}).get("orcid"),
                    "author_position": auth.get("author_position"),
                    "is_corresponding": auth.get("is_corresponding"),
                    "institutions": institutions,
                }
            )

        return {
            "paper_id": paper_id,
            "paper_title": title,
            "paper_doi": doi,
            "year": work.get("publication_year"),
            "cited_by_count": work.get("cited_by_count"),
            "venue": venue,
            "authors": authors,
            # aliases / raw
            "openalex_id": paper_id,
            "id": id_url,
            "display_name": title,
            "doi": doi,
            "publication_year": work.get("publication_year"),
        }

    @staticmethod
    def _dehydrate_author(author: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not author:
            return None
        id_url = author.get("id")
        author_id = to_short_openalex_id(id_url) or to_short_openalex_id(author.get("openalex_id"))
        summary_stats = author.get("summary_stats") or {}
        institution = None
        affiliations = author.get("affiliations") or []
        if isinstance(affiliations, list):
            for aff in affiliations:
                if not isinstance(aff, dict):
                    continue
                inst = aff.get("institution")
                if not isinstance(inst, dict):
                    continue
                name = inst.get("display_name") or inst.get("name")
                if isinstance(name, str) and name.strip():
                    institution = name.strip()
                    break
        return {
            "author_id": author_id,
            "author_name": author.get("display_name"),
            "orcid": author.get("orcid") or (author.get("ids") or {}).get("orcid"),
            "h_index": summary_stats.get("h_index") or author.get("h_index"),
            "works_count": author.get("works_count"),
            "cited_by_count": author.get("cited_by_count"),
            "institution": institution,
            "summary_stats": summary_stats,
            # aliases / raw
            "openalex_id": author_id,
            "id": id_url,
            "display_name": author.get("display_name"),
        }
