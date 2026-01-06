"""Phase-1 end-to-end pipeline: cited-by -> author h-index ranking -> reference contexts.

This pipeline composes existing modules:
- OpenAlex (match + cited-by list)
- Author h-index enrichment
- PDF fetch + fulltext extraction
- Reference-context extraction by referenced paper title

Outputs:
- A JSON file for selected candidates (max author h-index + cited_by_count)
- One JSON file per selected citing paper with extracted reference contexts
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pcra.get_pdf_fulltext import get_pdf_fulltext
from pcra.get_ref_ctx import get_paper_reference_context
from pcra.openalex import OpenAlexFacade
from pcra.pipelines.citations import enrich_authors_with_h_index

logger = logging.getLogger(__name__)


JsonDict = Dict[str, Any]
PathLike = Union[str, Path]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_max_author_h_index(work: JsonDict) -> Optional[int]:
    authors = work.get("authors") or []
    h_values = [a.get("h_index") for a in authors if isinstance(a.get("h_index"), int)]
    return max(h_values) if h_values else None


def _sort_key_by_max_h_index(work: JsonDict) -> Tuple[int, int, int, int, str]:
    max_h = compute_max_author_h_index(work)
    cited_by_count = work.get("cited_by_count")
    year = work.get("year")
    title = work.get("paper_title") or ""
    return (
        1 if max_h is None else 0,
        -(max_h or 0),
        -int(cited_by_count or 0),
        -int(year or 0),
        str(title),
    )


def rank_works_by_max_author_h_index(works: List[JsonDict]) -> List[JsonDict]:
    """Return a new list sorted by max(author h_index) desc, then cited_by_count/year."""
    return sorted(list(works), key=_sort_key_by_max_h_index)


def _write_json(path: Path, payload: JsonDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _summarize_candidate(work: JsonDict) -> JsonDict:
    authors = work.get("authors") or []
    max_h = compute_max_author_h_index(work)
    return {
        "paper_id": work.get("paper_id"),
        "paper_title": work.get("paper_title"),
        "paper_doi": work.get("paper_doi"),
        "year": work.get("year"),
        "cited_by_count": work.get("cited_by_count"),
        "venue": work.get("venue"),
        "max_author_h_index": max_h,
        "authors": [
            {
                "author_id": a.get("author_id"),
                "name": a.get("name"),
                "author_position": a.get("author_position"),
                "h_index": a.get("h_index"),
            }
            for a in authors
        ],
    }


@dataclass(frozen=True)
class E2EOutputs:
    out_dir: str
    cand_metrics_json: str
    contexts_dir: str
    fulltext_dir: str


def run_e2e_ref_ctx_get(
    paper_to_analyze: str,
    *,
    topk_citation_cand: int,
    topk_author_max_h_index_cand: int,
    out_dir: PathLike = "log/e2e_ref_ctx_get",
    # OpenAlex -> author metrics
    max_author_lookups: Optional[int] = None,
    # PDF -> fulltext
    pdf_query_suffix: str = " pdf",
    pdf_engine: str = "duckduckgo",
    fulltext_method: str = "pymupdfllm",
    truncate_long_pdf: bool = True,
    max_pages: int = 20,
    # Ref context
    window: int = 512,
    match_threshold: float = 0.8,
    # Re-run behavior
    reuse_existing: bool = True,
) -> JsonDict:
    """Run the Phase-1 E2E pipeline and write outputs to disk.

    Args:
        paper_to_analyze: Target paper title (query).
        topk_citation_cand: Take top-K citing works by cited_by_count.
        topk_author_max_h_index_cand: From those, take top-K by max(author h_index).
        out_dir: Output directory.
        max_author_lookups: Optional cap on how many unique authors to fetch h-index for.
        pdf_query_suffix: Query suffix used when searching PDFs (default: " pdf").
        pdf_engine: Search engine for `pcra.get_pdf.search_and_download`.
        fulltext_method: `pcra.get_pdf_fulltext.get_pdf_fulltext` method.
        truncate_long_pdf/max_pages: Long-PDF truncation controls.
        window/match_threshold: `pcra.get_ref_ctx.get_paper_reference_context` controls.
        reuse_existing: If a per-paper context JSON exists, skip regenerating it.

    Returns:
        A summary dict including paths and counts.
    """

    if topk_citation_cand <= 0:
        raise ValueError(f"topk_citation_cand must be > 0, got: {topk_citation_cand}")
    if topk_author_max_h_index_cand <= 0:
        raise ValueError(
            f"topk_author_max_h_index_cand must be > 0, got: {topk_author_max_h_index_cand}"
        )

    out_dir = Path(out_dir).expanduser()
    contexts_dir = out_dir / "paper_ref_contexts"
    fulltext_dir = out_dir / "fulltext"
    cand_metrics_json = out_dir / "cand_h_index_cited_by.json"

    facade = OpenAlexFacade()
    match_info = facade.work_match_by_title(paper_to_analyze, top_k=3, threshold=0.0)
    target = match_info.get("match") or {}
    if not target.get("paper_id"):
        raise RuntimeError(f"OpenAlex match failed for title: {paper_to_analyze!r}")

    target_title = target.get("paper_title") or paper_to_analyze
    logger.info("Target paper matched: %s (paper_id=%s)", target_title, target.get("paper_id"))

    cited_by = facade.work_cited_by(
        target["paper_id"],
        top_k=topk_citation_cand,
        sort="cited_by_count:desc,publication_year:desc",
    )

    enrich_authors_with_h_index(cited_by, client=facade.client, max_authors=max_author_lookups)
    ranked = rank_works_by_max_author_h_index(cited_by)
    cand_h_index_cited_by = ranked[:topk_author_max_h_index_cand]

    metrics_payload: JsonDict = {
        "generated_at": _utc_now_iso(),
        "paper_to_analyze": {
            "query_title": paper_to_analyze,
            "matched_title": target_title,
            "paper_id": target.get("paper_id"),
            "paper_doi": target.get("paper_doi"),
            "match_score": match_info.get("match_score"),
        },
        "params": {
            "topk_citation_cand": topk_citation_cand,
            "topk_author_max_h_index_cand": topk_author_max_h_index_cand,
            "max_author_lookups": max_author_lookups,
            "pdf_query_suffix": pdf_query_suffix,
            "pdf_engine": pdf_engine,
            "fulltext_method": fulltext_method,
            "truncate_long_pdf": truncate_long_pdf,
            "max_pages": max_pages,
            "window": window,
            "match_threshold": match_threshold,
        },
        "cand_h_index_cited_by": [_summarize_candidate(w) for w in cand_h_index_cited_by],
    }
    _write_json(cand_metrics_json, metrics_payload)

    success = 0
    attempted = 0

    for w in cand_h_index_cited_by:
        paper_id = w.get("paper_id") or "unknown"
        out_path = contexts_dir / f"{paper_id}.json"
        if reuse_existing and out_path.exists():
            logger.info("Skip existing context json: %s", out_path)
            continue

        attempted += 1
        paper_title = w.get("paper_title") or ""
        query = f"{paper_title}{pdf_query_suffix}".strip()
        pdf_path: Optional[str] = None
        pdf_error: Optional[str] = None
        fulltext_meta: Optional[JsonDict] = None
        fulltext_error: Optional[str] = None
        ref_ctx: Optional[JsonDict] = None

        try:
            from pcra.get_pdf import search_and_download as _search_and_download
        except Exception as e:
            pdf_error = f"get_pdf unavailable: {type(e).__name__}: {e}"
        else:
            try:
                pdf = _search_and_download(
                    query,
                    engine=pdf_engine,
                    paper_id=paper_id,
                    paper_title=paper_title,
                )
                if pdf is None:
                    pdf_error = f"PDF not found for query: {query!r}"
                else:
                    pdf_path = str(pdf)
            except Exception as e:
                pdf_error = f"{type(e).__name__}: {e}"

        if pdf_path and not pdf_error:
            try:
                ft = get_pdf_fulltext(
                    pdf_path,
                    method=fulltext_method,
                    truncate_long_pdf=truncate_long_pdf,
                    max_pages=max_pages,
                )
                fulltext_meta = {k: ft.get(k) for k in ["method", "pages_used", "page_count", "truncated", "elapsed_s"]}
                fulltext_path = fulltext_dir / f"{paper_id}.md"
                fulltext_path.parent.mkdir(parents=True, exist_ok=True)
                fulltext_path.write_text(ft.get("text") or "", encoding="utf-8")

                ref_ctx = get_paper_reference_context(
                    ft.get("text") or "",
                    target_title,
                    window=window,
                    match_threshold=match_threshold,
                )
                if not ref_ctx.get("ref_id") and target_title != paper_to_analyze:
                    alt = get_paper_reference_context(
                        ft.get("text") or "",
                        paper_to_analyze,
                        window=window,
                        match_threshold=match_threshold,
                    )
                    if alt.get("ref_id") or (alt.get("match_score") or 0.0) > (ref_ctx.get("match_score") or 0.0):
                        ref_ctx = alt
            except Exception as e:
                fulltext_error = f"{type(e).__name__}: {e}"

        if fulltext_error is None and (pdf_error or not pdf_path):
            fulltext_error = "skipped: pdf unavailable"

        if ref_ctx is None:
            if pdf_error or not pdf_path:
                ref_ctx_error = "skipped: pdf unavailable"
            elif fulltext_error:
                ref_ctx_error = "skipped: fulltext unavailable"
            else:
                ref_ctx_error = "skipped: unknown"
            ref_ctx = {
                "query_title": target_title,
                "ref_id": None,
                "match_score": 0.0,
                "reference_entry": None,
                "contexts": [],
                "error": ref_ctx_error,
            }

        payload: JsonDict = {
            "generated_at": _utc_now_iso(),
            "paper_to_analyze": {
                "query_title": paper_to_analyze,
                "matched_title": target_title,
                "paper_id": target.get("paper_id"),
                "paper_doi": target.get("paper_doi"),
            },
            "citing_paper": _summarize_candidate(w),
            "pdf": {
                "query": query,
                "engine": pdf_engine,
                "path": pdf_path,
                "error": pdf_error,
            },
            "fulltext": {
                "method": fulltext_method,
                "truncate_long_pdf": truncate_long_pdf,
                "max_pages": max_pages,
                "path": str((fulltext_dir / f"{paper_id}.md").resolve())
                if pdf_path and fulltext_error is None
                else None,
                "meta": fulltext_meta,
                "error": fulltext_error,
            },
            "ref_ctx": ref_ctx,
        }
        _write_json(out_path, payload)

        if ref_ctx and isinstance(ref_ctx.get("ref_id"), int):
            success += 1

    outputs = E2EOutputs(
        out_dir=str(out_dir),
        cand_metrics_json=str(cand_metrics_json),
        contexts_dir=str(contexts_dir),
        fulltext_dir=str(fulltext_dir),
    )
    return {
        "generated_at": _utc_now_iso(),
        "paper_to_analyze": paper_to_analyze,
        "matched_paper_id": target.get("paper_id"),
        "matched_paper_title": target_title,
        "cited_by_fetched": len(cited_by),
        "cand_h_index_cited_by": len(cand_h_index_cited_by),
        "context_attempted": attempted,
        "context_ref_id_found": success,
        "outputs": asdict(outputs),
    }
