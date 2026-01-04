"""End-to-end pipeline for single paper citation remark analysis (T1~T9)."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pcra.author import enrich_authors_with_metrics
from pcra.candidates import ensure_max_h_index_author, select_candidates
from pcra.core import RunContext
from pcra.dblp import query_publication_status
from pcra.fellow import lookup_fellow_status
from pcra.get_pdf import search_and_download
from pcra.get_pdf_fulltext import get_pdf_fulltext
from pcra.get_ref_ctx import get_paper_reference_context
from pcra.openalex import OpenAlexClient, OpenAlexFacade
from pcra.trace import TraceWriter
from pcra.remark_analy import load_llm_config, score_paper_contexts, write_paper_report, write_summary_report_v2

JsonDict = Dict[str, Any]
PathLike = Union[str, Path]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: JsonDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _sorted_authors_by_h_index(authors: List[JsonDict]) -> List[JsonDict]:
    def sort_key(a: JsonDict) -> Tuple[int, str]:
        h = a.get("h_index")
        h_val = h if isinstance(h, int) else -1
        return (-h_val, str(a.get("name") or ""))

    return sorted(authors, key=sort_key)


def _normalize_author_name(value: Optional[str]) -> str:
    if not value:
        return ""
    return " ".join(str(value).split()).strip().lower()


def _is_self_citation(target_author: Optional[str], authors: List[JsonDict]) -> Optional[bool]:
    if not target_author or not str(target_author).strip():
        return None
    target_norm = _normalize_author_name(target_author)
    if not target_norm:
        return None
    for author in authors:
        name = _normalize_author_name(author.get("name"))
        if name and name == target_norm:
            return True
    return False


def _copy_pdf(src: Path, dest_dir: Path, paper_id: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{paper_id}.pdf"
    try:
        shutil.copy2(src, dest_path)
    except Exception:
        return src
    return dest_path


def _build_topk_authors(
    authors: List[JsonDict],
    *,
    fellow_check_topK: int,
    llm_config_path: Optional[Path],
    fellow_web_search_topk: int,
    web_search_timeout_s: int,
    web_search_max_retries: int,
    cache_path: Optional[Path],
) -> Tuple[List[JsonDict], bool, List[str]]:
    sorted_authors = _sorted_authors_by_h_index(authors)
    topk_raw = sorted_authors[: max(0, int(fellow_check_topK))]
    topk_authors: List[JsonDict] = []
    errors: List[str] = []
    has_fellow = False

    for author in topk_raw:
        name = author.get("name")
        affiliation = author.get("affiliation")
        institutions = author.get("institutions") or []
        statuses, sources, error = lookup_fellow_status(
            str(name or ""),
            str(affiliation or "") if affiliation is not None else None,
            institutions=institutions if institutions else None,
            llm_config_path=llm_config_path,
            max_results=fellow_web_search_topk,
            timeout_s=web_search_timeout_s,
            max_retries=web_search_max_retries,
            cache_path=cache_path,
        )
        if error:
            errors.append(error)
        if any(v == "Yes" for v in statuses.values()):
            has_fellow = True
        topk_authors.append(
            {
                "author_id": author.get("author_id"),
                "name": name,
                "affiliation": affiliation,
                "institutions": institutions,
                "h_index": author.get("h_index"),
                "fellow_status": statuses,
                "fellow_status_sources": sources,
            }
        )

    return topk_authors, has_fellow, errors


@dataclass(frozen=True)
class E2EOutputs:
    res_dir: str
    log_dir: str
    trace_path: str
    ref_ctx_dir: str
    ref_ctx_scored_dir: str
    reports_dir: str
    summary_md: str
    summary_json: str


def run_e2e_single_paper(
    paper_to_analyze: str,
    *,
    target_author: Optional[str] = None,
    llm_config_path: Optional[PathLike] = None,
    res_dir: PathLike = "log/e2e_single_paper_run",
    log_dir: PathLike = "log/trace",
    cited_by_topK: int = 30,
    fellow_check_topK: int = 5,
    fellow_web_search_topk: int = 5,
    roll_back_paper_topK: int = 10,
    openalex_match_threshold: float = 0.6,
    ref_ctx_match_threshold: float = 0.8,
    window_size: int = 512,
    pdf_query_suffix: str = " pdf",
    pdf_engine: str = "duckduckgo",
    fulltext_method: str = "pymupdfllm",
    truncate_long_pdf: bool = True,
    max_pages: int = 30,
    max_author_lookups: Optional[int] = None,
    max_contexts: Optional[int] = None,
    dry_run: bool = False,
    skip_scored: bool = True,
    # External dependencies
    openalex_timeout_s: int = 30,
    openalex_max_retries: int = 3,
    dblp_min_sim: float = 0.92,
    dblp_hits: int = 20,
    dblp_timeout_s: int = 20,
    dblp_max_retries: int = 2,
    web_search_timeout_s: int = 60,
    web_search_max_retries: int = 2,
) -> JsonDict:
    """Run the refactored T1~T9 pipeline for one target paper."""

    if cited_by_topK <= 0:
        raise ValueError(f"cited_by_topK must be > 0, got: {cited_by_topK}")
    if fellow_check_topK < 0:
        raise ValueError(f"fellow_check_topK must be >= 0, got: {fellow_check_topK}")
    if roll_back_paper_topK < 0:
        raise ValueError(f"roll_back_paper_topK must be >= 0, got: {roll_back_paper_topK}")
    if window_size <= 0:
        raise ValueError(f"window_size must be > 0, got: {window_size}")
    if max_pages <= 0:
        raise ValueError(f"max_pages must be > 0, got: {max_pages}")

    params_snapshot = {
        "cited_by_topK": cited_by_topK,
        "fellow_check_topK": fellow_check_topK,
        "fellow_web_search_topk": fellow_web_search_topk,
        "roll_back_paper_topK": roll_back_paper_topK,
        "target_author": target_author,
        "openalex_match_threshold": openalex_match_threshold,
        "ref_ctx_match_threshold": ref_ctx_match_threshold,
        "window_size": window_size,
        "pdf_query_suffix": pdf_query_suffix,
        "pdf_engine": pdf_engine,
        "fulltext_method": fulltext_method,
        "truncate_long_pdf": truncate_long_pdf,
        "max_pages": max_pages,
        "max_author_lookups": max_author_lookups,
        "max_contexts": max_contexts,
        "dry_run": dry_run,
        "skip_scored": skip_scored,
        "openalex": {"timeout_s": openalex_timeout_s, "max_retries": openalex_max_retries},
        "dblp": {
            "min_sim": dblp_min_sim,
            "hits": dblp_hits,
            "timeout_s": dblp_timeout_s,
            "max_retries": dblp_max_retries,
        },
        "web_search": {
            "timeout_s": web_search_timeout_s,
            "max_retries": web_search_max_retries,
        },
    }

    run_ctx = RunContext.create(
        paper_to_analyze=paper_to_analyze,
        llm_config_path=str(llm_config_path) if llm_config_path else None,
        res_dir=str(res_dir),
        log_dir=str(log_dir),
        params=params_snapshot,
    )
    trace = TraceWriter.from_log_dir(run_ctx.run_id, run_ctx.log_dir)

    trace.write(
        "T1",
        core={
            "run_id": run_ctx.run_id,
            "paper_to_analyze": paper_to_analyze,
            "res_dir": str(run_ctx.res_dir),
            "log_dir": str(run_ctx.log_dir),
        },
        params={"params_frozen": run_ctx.params_frozen},
    )

    openalex_client = OpenAlexClient(timeout_s=openalex_timeout_s, max_retries=openalex_max_retries)
    openalex_facade = OpenAlexFacade(client=openalex_client)

    match_info = openalex_facade.work_match_by_title(
        paper_to_analyze, top_k=3, threshold=openalex_match_threshold
    )
    match = match_info.get("match") or {}
    if not match.get("paper_id"):
        raise RuntimeError(f"OpenAlex match failed for title: {paper_to_analyze!r}")

    paper_to_analyze_meta = {
        "query_title": paper_to_analyze,
        "matched_title": match.get("paper_title") or paper_to_analyze,
        "paper_id": match.get("paper_id"),
        "paper_doi": match.get("paper_doi"),
        "target_author": target_author,
    }

    trace.write(
        "T2",
        core={"paper_to_analyze": paper_to_analyze_meta},
        params={"openalex_match_threshold": openalex_match_threshold},
        meta={
            "match_score": match_info.get("match_score"),
            "is_confident": match_info.get("is_confident"),
        },
    )

    cited_by = openalex_facade.work_cited_by(
        match["paper_id"],
        top_k=cited_by_topK,
    )
    cited_by_raw_count = len(cited_by)

    trace.write(
        "T3",
        core={"paper_id": match.get("paper_id"), "cited_by": cited_by},
        params={"cited_by_topK": cited_by_topK},
        meta={"cited_by_count": len(cited_by)},
    )

    published: List[JsonDict] = []
    dblp_errors = 0
    status_counts = {"published": 0, "informal": 0, "unknown": 0}
    for work in cited_by:
        title = work.get("paper_title") or ""
        if not str(title).strip():
            status, meta = {"status": "unknown"}, {"error": "missing_title"}
        else:
            status, meta = query_publication_status(
                title,
                min_sim=dblp_min_sim,
                hits=dblp_hits,
                timeout_s=dblp_timeout_s,
                max_retries=dblp_max_retries,
            )
        work["publication_status"] = status
        if meta.get("error"):
            dblp_errors += 1
        status_key = (status.get("status") or "unknown").lower()
        if status_key not in status_counts:
            status_key = "unknown"
        status_counts[status_key] += 1
        if status_key == "published":
            published.append(work)

    cited_by = published
    trace.write(
        "T3a",
        core={"cited_by": cited_by},
        params={
            "dblp_min_sim": dblp_min_sim,
            "dblp_hits": dblp_hits,
            "dblp_timeout_s": dblp_timeout_s,
            "dblp_max_retries": dblp_max_retries,
        },
        meta={
            "dblp_errors": dblp_errors,
            "status_counts": status_counts,
            "published_count": len(cited_by),
        },
    )

    enrich_authors_with_metrics(
        cited_by,
        client=openalex_client,
        max_authors=max_author_lookups,
    )

    trace.write(
        "T4a",
        core={"cited_by_enriched": cited_by},
        params={"max_author_lookups": max_author_lookups},
    )

    cache_path = run_ctx.dirs["cache_dir"] / "fellow_lookup.json"
    has_fellow_count = 0
    fellow_errors = 0
    topk_authors_total = 0
    for work in cited_by:
        authors = work.get("authors") or []
        topk_authors, has_fellow, errors = _build_topk_authors(
            authors,
            fellow_check_topK=fellow_check_topK,
            llm_config_path=Path(llm_config_path) if llm_config_path else None,
            fellow_web_search_topk=fellow_web_search_topk,
            web_search_timeout_s=web_search_timeout_s,
            web_search_max_retries=web_search_max_retries,
            cache_path=cache_path,
        )
        work["topk_authors"] = topk_authors
        work["has_fellow_topk"] = has_fellow
        if has_fellow:
            has_fellow_count += 1
        fellow_errors += len(errors)
        topk_authors_total += len(topk_authors)
        ensure_max_h_index_author(work)

    trace.write(
        "T4b",
        core={"cited_by_enriched": cited_by},
        params={
            "fellow_check_topK": fellow_check_topK,
            "fellow_web_search_topk": fellow_web_search_topk,
        },
        meta={
            "has_fellow_count": has_fellow_count,
            "fellow_errors": fellow_errors,
            "topk_authors_total": topk_authors_total,
        },
    )

    candidates_selected = select_candidates(
        cited_by,
        roll_back_paper_topK=roll_back_paper_topK,
    )

    selection_reason = None
    if candidates_selected:
        selection_reason = candidates_selected[0].get("selection_reason")

    trace.write(
        "T4c",
        core={"candidates_selected": candidates_selected},
        params={"roll_back_paper_topK": roll_back_paper_topK},
        meta={"selected_count": len(candidates_selected), "selection_reason": selection_reason},
    )

    ref_ctx_dir = run_ctx.dirs["ref_ctx_dir"]
    ref_ctx_scored_dir = run_ctx.dirs["ref_ctx_scored_dir"]
    reports_dir = run_ctx.dirs["reports_dir"]
    paper_reports_dir = run_ctx.dirs["paper_reports_dir"]
    summary_md_path = reports_dir / "summary.md"
    summary_json_path = run_ctx.res_dir / "summary.json"

    llm_config = None
    if not dry_run:
        llm_config = load_llm_config(Path(llm_config_path) if llm_config_path else None)

    scored_payloads: List[JsonDict] = []
    for work in candidates_selected:
        paper_id = work.get("paper_id") or "unknown"
        paper_title = work.get("paper_title") or ""
        query = f"{paper_title}{pdf_query_suffix}".strip()
        self_citation = _is_self_citation(target_author, work.get("authors") or [])

        pdf_path: Optional[str] = None
        pdf_error: Optional[str] = None
        fulltext_error: Optional[str] = None
        fulltext_meta: Optional[JsonDict] = None
        ref_ctx: Optional[JsonDict] = None
        ref_ctx_error: Optional[str] = None
        fulltext_path: Optional[Path] = None

        if not paper_title.strip():
            pdf_error = "missing_paper_title"
        else:
            try:
                pdf = search_and_download(query, engine=pdf_engine)
                if pdf is None:
                    pdf_error = f"PDF not found for query: {query!r}"
                else:
                    pdf_path = str(_copy_pdf(Path(pdf), run_ctx.dirs["pdf_dir"], paper_id))
            except Exception as exc:
                pdf_error = f"{type(exc).__name__}: {exc}"

        trace.write(
            "T5",
            core={"paper_id": paper_id, "paper_title": paper_title},
            params={"pdf_query_suffix": pdf_query_suffix, "pdf_engine": pdf_engine},
            meta={"pdf_path": pdf_path, "pdf_error": pdf_error, "query": query},
        )

        if pdf_path and not pdf_error:
            try:
                ft = get_pdf_fulltext(
                    pdf_path,
                    method=fulltext_method,
                    truncate_long_pdf=truncate_long_pdf,
                    max_pages=max_pages,
                )
                fulltext_meta = {
                    "method": ft.get("method"),
                    "pages_used": ft.get("pages_used"),
                    "page_count": ft.get("page_count"),
                    "truncated": ft.get("truncated"),
                    "elapsed_s": ft.get("elapsed_s"),
                }
                fulltext_path = run_ctx.dirs["fulltext_dir"] / f"{paper_id}.md"
                fulltext_path.write_text(ft.get("text") or "", encoding="utf-8")
            except Exception as exc:
                fulltext_error = f"{type(exc).__name__}: {exc}"
        else:
            fulltext_error = "skipped: pdf unavailable"

        trace.write(
            "T6",
            core={"paper_id": paper_id},
            params={
                "fulltext_method": fulltext_method,
                "truncate_long_pdf": truncate_long_pdf,
                "max_pages": max_pages,
            },
            meta={"fulltext_meta": fulltext_meta, "fulltext_error": fulltext_error},
        )

        if fulltext_error is None and fulltext_path is not None:
            try:
                fulltext_text = fulltext_path.read_text(encoding="utf-8")
                ref_ctx = get_paper_reference_context(
                    fulltext_text,
                    paper_to_analyze_meta["matched_title"],
                    window=window_size,
                    match_threshold=ref_ctx_match_threshold,
                )
                if not ref_ctx.get("ref_id") and paper_to_analyze_meta["matched_title"] != paper_to_analyze:
                    alt = get_paper_reference_context(
                        fulltext_text,
                        paper_to_analyze,
                        window=window_size,
                        match_threshold=ref_ctx_match_threshold,
                    )
                    if alt.get("ref_id") or (alt.get("match_score") or 0.0) > (
                        ref_ctx.get("match_score") or 0.0
                    ):
                        ref_ctx = alt
            except Exception as exc:
                ref_ctx_error = f"{type(exc).__name__}: {exc}"

        if ref_ctx is None:
            if ref_ctx_error:
                ref_ctx_error = f"ref_ctx_failed: {ref_ctx_error}"
            elif pdf_error or not pdf_path:
                ref_ctx_error = "skipped: pdf unavailable"
            elif fulltext_error:
                ref_ctx_error = "skipped: fulltext unavailable"
            else:
                ref_ctx_error = "skipped: unknown"
            ref_ctx = {
                "query_title": paper_to_analyze_meta["matched_title"],
                "ref_id": None,
                "match_score": 0.0,
                "reference_entry": None,
                "contexts": [],
                "error": ref_ctx_error,
            }

        for ctx in ref_ctx.get("contexts") or []:
            ctx.setdefault("context_window_size", window_size)

        ref_ctx["context_window_size"] = window_size

        trace.write(
            "T7",
            core={"paper_id": paper_id, "contexts_count": len(ref_ctx.get("contexts") or [])},
            params={"window_size": window_size, "ref_ctx_match_threshold": ref_ctx_match_threshold},
            meta={
                "reference_entry": ref_ctx.get("reference_entry"),
                "match_score": ref_ctx.get("match_score"),
                "citation_style": ref_ctx.get("citation_style_detected"),
                "ref_ctx_error": ref_ctx.get("error"),
            },
        )

        payload: JsonDict = {
            "generated_at": _utc_now_iso(),
            "run_id": run_ctx.run_id,
            "paper_to_analyze": paper_to_analyze_meta,
            "citing_paper": {
                "paper_id": work.get("paper_id"),
                "paper_title": work.get("paper_title"),
                "year": work.get("year"),
                "cited_by_count": work.get("cited_by_count"),
                "publication_status": work.get("publication_status"),
                "topk_authors": work.get("topk_authors"),
                "has_fellow_topk": work.get("has_fellow_topk"),
                "selection_reason": work.get("selection_reason"),
                "max_h_index_author": work.get("max_h_index_author"),
                "self_citation": self_citation,
            },
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
                "path": str((run_ctx.dirs["fulltext_dir"] / f"{paper_id}.md").resolve())
                if pdf_path and fulltext_error is None
                else None,
                "meta": fulltext_meta,
                "error": fulltext_error,
            },
            "ref_ctx": ref_ctx,
        }

        context_path = ref_ctx_dir / f"{paper_id}.json"
        _write_json(context_path, payload)

        scored_path = ref_ctx_scored_dir / f"{paper_id}.json"
        scored_summary = score_paper_contexts(
            context_path,
            scored_path,
            config=llm_config,
            dry_run=dry_run,
            max_contexts=max_contexts,
            skip_scored=skip_scored,
        )
        scored_data = json.loads(scored_path.read_text(encoding="utf-8"))
        scored_payloads.append(scored_data)

        scored_contexts = (scored_data.get("ref_ctx") or {}).get("contexts_scored") or (
            scored_data.get("ref_ctx") or {}
        ).get("contexts") or []
        remark_scores = [
            ctx.get("remark_score") for ctx in scored_contexts if isinstance(ctx.get("remark_score"), int)
        ]
        trace.write(
            "T8",
            core={"paper_id": paper_id, "contexts_count": scored_summary.get("contexts_total")},
            params={"max_contexts": max_contexts, "dry_run": dry_run, "skip_scored": skip_scored},
            meta={
                "scored_path": str(scored_path),
                "scored": scored_summary.get("scored"),
                "errors": scored_summary.get("errors"),
                "remark_scores": remark_scores[:5],
                "remark_scores_count": len(remark_scores),
            },
        )

        paper_report_path = paper_reports_dir / f"{paper_id}.md"
        write_paper_report(paper_report_path, scored_data, paper_id)

    write_summary_report_v2(
        summary_md_path,
        summary_json_path,
        scored_payloads=scored_payloads,
        paper_to_analyze=paper_to_analyze_meta,
    )

    trace.write(
        "T9",
        core={"summary_json_path": str(summary_json_path), "summary_md_path": str(summary_md_path)},
        params={"fellow_check_topK": fellow_check_topK, "window_size": window_size},
        meta={"reports_count": len(scored_payloads)},
    )

    outputs = E2EOutputs(
        res_dir=str(run_ctx.res_dir),
        log_dir=str(run_ctx.log_dir),
        trace_path=str(trace.trace_path),
        ref_ctx_dir=str(ref_ctx_dir),
        ref_ctx_scored_dir=str(ref_ctx_scored_dir),
        reports_dir=str(reports_dir),
        summary_md=str(summary_md_path),
        summary_json=str(summary_json_path),
    )

    return {
        "generated_at": _utc_now_iso(),
        "run_id": run_ctx.run_id,
        "paper_to_analyze": paper_to_analyze_meta,
        "cited_by_fetched": cited_by_raw_count,
        "candidates_selected": len(candidates_selected),
        "outputs": asdict(outputs),
    }
