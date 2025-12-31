"""Phase-2 pipeline: reference contexts + LLM remark analysis."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pcra.pipelines.e2e_ref_ctx_get import run_e2e_ref_ctx_get
from pcra.remark_analy import (
    build_paper_summary,
    load_llm_config,
    score_paper_contexts,
    write_paper_report,
    write_summary_report,
)

JsonDict = Dict[str, Any]
PathLike = Union[str, Path]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> JsonDict:
    return json.loads(path.read_text(encoding="utf-8"))


def _select_context_file(contexts_dir: Path, paper_id: Optional[str]) -> Path:
    if paper_id:
        path = contexts_dir / f"{paper_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"context json not found: {path}")
        return path

    candidates = sorted(contexts_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no context json files found under: {contexts_dir}")

    for path in candidates:
        data = _load_json(path)
        contexts = (data.get("ref_ctx") or {}).get("contexts") or []
        if contexts:
            return path

    return candidates[0]


def _collect_scored_paths(scored_dir: Path) -> List[Path]:
    return sorted(scored_dir.glob("*.json"))


@dataclass(frozen=True)
class E2ERemarkOutputs:
    out_dir: str
    contexts_dir: str
    scored_dir: str
    reports_dir: str
    summary_md: str
    summary_json: str


def run_e2e_ref_ctx_get_and_remark_analy(
    paper_to_analyze: str,
    *,
    topk_citation_cand: int,
    topk_author_max_h_index_cand: int,
    out_dir: PathLike = "log/e2e_ref_ctx_get_and_remark_analy_run",
    # OpenAlex -> author metrics
    max_author_lookups: Optional[int] = None,
    # PDF -> fulltext
    pdf_query_suffix: str = " pdf",
    pdf_engine: str = "duckduckgo",
    fulltext_method: str = "pymupdfllm",
    truncate_long_pdf: bool = True,
    max_pages: int = 30,
    # Ref context
    window: int = 512,
    match_threshold: float = 0.8,
    # Re-run behavior
    reuse_existing: bool = True,
    # Remark analysis
    paper_id: Optional[str] = None,
    max_contexts: Optional[int] = None,
    dry_run: bool = False,
    llm_config_path: Optional[PathLike] = None,
    skip_scored: bool = True,
) -> JsonDict:
    """Run Phase-1 context extraction and Phase-2 remark analysis."""

    out_dir = Path(out_dir).expanduser()
    contexts_dir = out_dir / "paper_ref_contexts"
    scored_dir = out_dir / "paper_ref_contexts_scored"
    reports_dir = out_dir / "reports"
    summary_md = reports_dir / "summary.md"
    summary_json = reports_dir / "summary.json"

    phase1_summary = run_e2e_ref_ctx_get(
        paper_to_analyze,
        topk_citation_cand=topk_citation_cand,
        topk_author_max_h_index_cand=topk_author_max_h_index_cand,
        out_dir=out_dir,
        max_author_lookups=max_author_lookups,
        pdf_query_suffix=pdf_query_suffix,
        pdf_engine=pdf_engine,
        fulltext_method=fulltext_method,
        truncate_long_pdf=truncate_long_pdf,
        max_pages=max_pages,
        window=window,
        match_threshold=match_threshold,
        reuse_existing=reuse_existing,
    )

    context_path = _select_context_file(contexts_dir, paper_id)
    selected_paper_id = context_path.stem
    scored_path = scored_dir / f"{selected_paper_id}.json"

    if scored_path.exists() and reuse_existing:
        scored_summary = {
            "input_path": str(context_path),
            "output_path": str(scored_path),
            "skipped": "reuse_existing",
        }
    else:
        config = None if dry_run else load_llm_config(Path(llm_config_path) if llm_config_path else None)
        scored_summary = score_paper_contexts(
            context_path,
            scored_path,
            config=config,
            dry_run=dry_run,
            max_contexts=max_contexts,
            skip_scored=skip_scored,
        )

    scored_paths = _collect_scored_paths(scored_dir)
    summaries: List[JsonDict] = []
    overall_scores: List[int] = []
    for path in scored_paths:
        data = _load_json(path)
        for ctx in (data.get("ref_ctx") or {}).get("contexts") or []:
            score = ctx.get("remark_score")
            if isinstance(score, int):
                overall_scores.append(score)
        paper_summary = build_paper_summary(data)
        if not paper_summary.get("paper_id"):
            paper_summary["paper_id"] = path.stem
        summaries.append(paper_summary)
        paper_md = reports_dir / "paper" / f"{path.stem}.md"
        write_paper_report(paper_md, data, path.stem)

    write_summary_report(summary_md, summary_json, summaries=summaries, overall_scores=overall_scores)

    outputs = E2ERemarkOutputs(
        out_dir=str(out_dir),
        contexts_dir=str(contexts_dir),
        scored_dir=str(scored_dir),
        reports_dir=str(reports_dir),
        summary_md=str(summary_md),
        summary_json=str(summary_json),
    )

    return {
        "generated_at": _utc_now_iso(),
        "phase1_summary": phase1_summary,
        "selected_paper_id": selected_paper_id,
        "scored_summary": scored_summary,
        "reports_count": len(summaries),
        "outputs": asdict(outputs),
    }
