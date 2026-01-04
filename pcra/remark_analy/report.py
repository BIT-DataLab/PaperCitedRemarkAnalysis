"""Report rendering for remark analysis."""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

JsonDict = Dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: JsonDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _is_int_score(value: Any) -> bool:
    return isinstance(value, int)


def _snippet(text: str, limit: int = 260) -> str:
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def _score_bucket(score: int) -> str:
    if score <= 3:
        return "neg"
    if score <= 6:
        return "neutral"
    return "pos"


def _score_stats(scores: List[int]) -> Dict[str, Optional[float]]:
    if not scores:
        return {"mean": None, "median": None}
    return {
        "mean": float(statistics.mean(scores)),
        "median": float(statistics.median(scores)),
    }


def _format_fellow_status(status: Optional[Dict[str, Any]]) -> str:
    if not status:
        return "Unknown"
    ieee = status.get("ieee") or "Unknown"
    acm = status.get("acm") or "Unknown"
    aaai = status.get("aaai") or "Unknown"
    return f"IEEE={ieee}, ACM={acm}, AAAI={aaai}"


def build_paper_summary(data: JsonDict) -> JsonDict:
    ref_ctx = data.get("ref_ctx") or {}
    contexts = ref_ctx.get("contexts") or ref_ctx.get("contexts_scored") or []

    scores: List[int] = []
    errors = 0
    bucket_counts = {"neg": 0, "neutral": 0, "pos": 0}

    for ctx in contexts:
        if ctx.get("remark_error"):
            errors += 1
        score = ctx.get("remark_score")
        if _is_int_score(score):
            scores.append(score)
            bucket_counts[_score_bucket(score)] += 1

    stats = _score_stats(scores)
    citing = data.get("citing_paper") or {}

    return {
        "paper_id": citing.get("paper_id"),
        "citing_title": citing.get("paper_title"),
        "contexts_total": len(contexts),
        "scored": len(scores),
        "errors": errors,
        "mean_score": stats["mean"],
        "median_score": stats["median"],
        "bucket_counts": bucket_counts,
    }


def _top_contexts(contexts: Iterable[JsonDict], *, top_n: int, reverse: bool) -> List[JsonDict]:
    scored: List[Tuple[int, int, JsonDict]] = []
    for idx, ctx in enumerate(contexts):
        score = ctx.get("remark_score")
        if not _is_int_score(score):
            continue
        scored.append((int(score), idx, ctx))

    scored.sort(key=lambda x: (x[0], -x[1]), reverse=reverse)
    items: List[JsonDict] = []
    for score, _, ctx in scored[:top_n]:
        items.append(
            {
                "remark_score": score,
                "reason": ctx.get("reason"),
                "context": _snippet(str(ctx.get("context") or "")),
                "match_text": ctx.get("match_text"),
            }
        )
    return items


def render_paper_report(data: JsonDict, paper_id: str, *, top_n: int = 3) -> str:
    summary = build_paper_summary(data)
    ref_ctx = data.get("ref_ctx") or {}
    contexts = ref_ctx.get("contexts") or ref_ctx.get("contexts_scored") or []
    citing = data.get("citing_paper") or {}
    target = data.get("paper_to_analyze") or {}

    top_pos = _top_contexts(contexts, top_n=top_n, reverse=True)
    top_neg = _top_contexts(contexts, top_n=top_n, reverse=False)

    def _fmt_item(item: JsonDict) -> str:
        return (
            f"- score={item.get('remark_score')} "
            f"marker={item.get('match_text')} "
            f"reason={item.get('reason')} "
            f"context={item.get('context')}"
        )

    max_author = citing.get("max_h_index_author") or {}
    topk_authors = citing.get("topk_authors") or []

    lines = [
        f"# Paper Report: {paper_id}",
        "",
        "## Citing Paper",
        f"- title: {citing.get('paper_title')}",
        f"- year: {citing.get('year')}",
        f"- cited_by_count: {citing.get('cited_by_count')}",
        f"- selection_reason: {citing.get('selection_reason')}",
        f"- has_fellow_topk: {citing.get('has_fellow_topk')}",
    ]
    if max_author:
        lines.append(
            f"- max_h_index_author: {max_author.get('name')} "
            f"({max_author.get('affiliation')}), h_index={max_author.get('h_index')}"
        )
    elif citing.get("max_author_h_index") is not None:
        lines.append(f"- max_author_h_index: {citing.get('max_author_h_index')}")

    lines += [
        "",
        "## Target Paper",
        f"- query_title: {target.get('query_title')}",
        f"- matched_title: {target.get('matched_title')}",
        f"- paper_id: {target.get('paper_id')}",
    ]
    if topk_authors:
        lines += ["", "## TopK Authors"]
        for author in topk_authors:
            lines.append(
                f"- {author.get('name')} ({author.get('affiliation')}), "
                f"h_index={author.get('h_index')}, "
                f"fellow_status={_format_fellow_status(author.get('fellow_status'))}"
            )

    lines += [
        "",
        "## Scoring Summary",
        f"- contexts_total: {summary.get('contexts_total')}",
        f"- scored: {summary.get('scored')}",
        f"- errors: {summary.get('errors')}",
        f"- mean_score: {summary.get('mean_score')}",
        f"- median_score: {summary.get('median_score')}",
        (
            "- buckets(0-3/4-6/7-10): "
            f"{summary.get('bucket_counts', {}).get('neg')}/"
            f"{summary.get('bucket_counts', {}).get('neutral')}/"
            f"{summary.get('bucket_counts', {}).get('pos')}"
        ),
        "",
        "## Top Positive Contexts",
    ]

    if top_pos:
        lines.extend(_fmt_item(item) for item in top_pos)
    else:
        lines.append("- (none)")

    lines.extend(["", "## Top Negative Contexts"])
    if top_neg:
        lines.extend(_fmt_item(item) for item in top_neg)
    else:
        lines.append("- (none)")

    return "\n".join(lines) + "\n"


def write_paper_report(path: Path, data: JsonDict, paper_id: str, *, top_n: int = 3) -> None:
    _write_text(path, render_paper_report(data, paper_id, top_n=top_n))


def render_summary_report(
    summaries: List[JsonDict],
    *,
    overall_scores: Optional[List[int]] = None,
) -> Tuple[str, JsonDict]:
    total_contexts = 0
    total_scored = 0
    total_errors = 0
    agg_buckets = {"neg": 0, "neutral": 0, "pos": 0}
    weighted_sum = 0.0
    weighted_count = 0

    for summary in summaries:
        total_contexts += int(summary.get("contexts_total") or 0)
        total_scored += int(summary.get("scored") or 0)
        total_errors += int(summary.get("errors") or 0)
        bucket_counts = summary.get("bucket_counts") or {}
        for key in agg_buckets:
            agg_buckets[key] += int(bucket_counts.get(key) or 0)
        if summary.get("mean_score") is not None and summary.get("scored"):
            weighted_sum += float(summary.get("mean_score") or 0.0) * int(summary.get("scored") or 0)
            weighted_count += int(summary.get("scored") or 0)

    if overall_scores:
        stats = _score_stats(overall_scores)
        mean_score = stats.get("mean")
        median_score = stats.get("median")
    else:
        mean_score = (weighted_sum / weighted_count) if weighted_count > 0 else None
        median_score = None

    lines = [
        "# Summary Report",
        "",
        "## Overall",
        f"- total_contexts: {total_contexts}",
        f"- scored: {total_scored}",
        f"- errors: {total_errors}",
        f"- mean_score: {mean_score}",
        f"- median_score: {median_score}",
        f"- buckets(0-3/4-6/7-10): {agg_buckets['neg']}/{agg_buckets['neutral']}/{agg_buckets['pos']}",
        "",
        "## Per Paper",
        "| paper_id | citing_title | contexts | scored | mean | neg | neutral | pos |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for summary in summaries:
        paper_id = summary.get("paper_id") or ""
        title = str(summary.get("citing_title") or "").replace("|", "/")
        buckets = summary.get("bucket_counts") or {}
        lines.append(
            f"| {paper_id} | {title} | {summary.get('contexts_total')} | "
            f"{summary.get('scored')} | {summary.get('mean_score')} | "
            f"{buckets.get('neg')} | {buckets.get('neutral')} | {buckets.get('pos')} |"
        )

    summary_json = {
        "generated_at": _utc_now_iso(),
        "total_contexts": total_contexts,
        "total_scored": total_scored,
        "total_errors": total_errors,
        "bucket_counts": agg_buckets,
        "per_paper": summaries,
    }

    return "\n".join(lines) + "\n", summary_json


def write_summary_report(
    md_path: Path,
    json_path: Path,
    *,
    summaries: List[JsonDict],
    overall_scores: Optional[List[int]] = None,
) -> None:
    md_text, json_payload = render_summary_report(summaries, overall_scores=overall_scores)
    _write_text(md_path, md_text)
    _write_json(json_path, json_payload)


def build_cited_paper_remarks(scored_payloads: List[JsonDict]) -> List[JsonDict]:
    remarks: List[JsonDict] = []
    for data in scored_payloads:
        ref_ctx = data.get("ref_ctx") or {}
        contexts = ref_ctx.get("contexts_scored") or ref_ctx.get("contexts") or []
        citing = data.get("citing_paper") or {}
        remarks.append(
            {
                "paper_title": citing.get("paper_title"),
                "topk_authors": [
                    {
                        "author_id": a.get("author_id"),
                        "name": a.get("name"),
                        "affiliation": a.get("affiliation"),
                        "institutions": a.get("institutions"),
                        "last_known_institutions": a.get("last_known_institutions"),
                        "h_index": a.get("h_index"),
                        "fellow_status": a.get("fellow_status"),
                    }
                    for a in (citing.get("topk_authors") or [])
                ],
                "contexts": [
                    {
                        "context": ctx.get("context"),
                        "context_window_size": ctx.get("context_window_size"),
                        "remark_score": ctx.get("remark_score"),
                        "reason": ctx.get("reason"),
                    }
                    for ctx in contexts
                ],
            }
        )
    return remarks


def render_summary_report_v2(
    scored_payloads: List[JsonDict],
    *,
    paper_to_analyze: Optional[Dict[str, Any]] = None,
) -> Tuple[str, JsonDict]:
    summaries = [build_paper_summary(data) for data in scored_payloads]
    overall_scores: List[int] = []
    for data in scored_payloads:
        ref_ctx = data.get("ref_ctx") or {}
        contexts = ref_ctx.get("contexts_scored") or ref_ctx.get("contexts") or []
        for ctx in contexts:
            score = ctx.get("remark_score")
            if _is_int_score(score):
                overall_scores.append(score)

    if paper_to_analyze is None:
        paper_to_analyze = (scored_payloads[0].get("paper_to_analyze") if scored_payloads else {}) or {}
    target = paper_to_analyze or {}
    cited_paper_remarks = build_cited_paper_remarks(scored_payloads)

    total_contexts = sum(int(s.get("contexts_total") or 0) for s in summaries)
    total_scored = sum(int(s.get("scored") or 0) for s in summaries)
    total_errors = sum(int(s.get("errors") or 0) for s in summaries)
    overall_stats = _score_stats(overall_scores)

    md_lines = [
        "# Summary Report",
        "",
        "## Target Paper",
        f"- query_title: {target.get('query_title')}",
        f"- matched_title: {target.get('matched_title')}",
        f"- paper_id: {target.get('paper_id')}",
        "",
        "## Overall",
        f"- total_contexts: {total_contexts}",
        f"- scored: {total_scored}",
        f"- errors: {total_errors}",
        f"- mean_score: {overall_stats.get('mean')}",
        f"- median_score: {overall_stats.get('median')}",
        "",
        "## Per Paper",
    ]

    for data in scored_payloads:
        citing = data.get("citing_paper") or {}
        ref_ctx = data.get("ref_ctx") or {}
        contexts = ref_ctx.get("contexts_scored") or ref_ctx.get("contexts") or []
        max_author = citing.get("max_h_index_author") or {}
        md_lines.extend(
            [
                f"### {citing.get('paper_title')}",
                f"- paper_id: {citing.get('paper_id')}",
                f"- contexts: {len(contexts)}",
                f"- has_fellow_topk: {citing.get('has_fellow_topk')}",
            ]
        )
        if max_author:
            md_lines.append(
                f"- max_h_index_author: {max_author.get('name')} "
                f"({max_author.get('affiliation')}), h_index={max_author.get('h_index')}"
            )
        topk_authors = citing.get("topk_authors") or []
        if topk_authors:
            joined = ", ".join(a.get("name") or "" for a in topk_authors)
            md_lines.append(f"- topk_authors: {joined}")
        md_lines.append("")

    summary_json = {
        "generated_at": _utc_now_iso(),
        "paper_to_analyze": {
            "query_title": target.get("query_title"),
            "matched_title": target.get("matched_title"),
            "paper_id": target.get("paper_id"),
        },
        "cited_paper_remarks": cited_paper_remarks,
    }

    return "\n".join(md_lines) + "\n", summary_json


def write_summary_report_v2(
    md_path: Path,
    json_path: Path,
    *,
    scored_payloads: List[JsonDict],
    paper_to_analyze: Optional[Dict[str, Any]] = None,
) -> None:
    md_text, json_payload = render_summary_report_v2(scored_payloads, paper_to_analyze=paper_to_analyze)
    _write_text(md_path, md_text)
    _write_json(json_path, json_payload)
