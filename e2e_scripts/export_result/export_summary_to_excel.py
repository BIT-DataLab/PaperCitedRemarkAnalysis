#!/usr/bin/env python3
"""
python e2e_scripts/export_result/export_summary_to_excel.py --trace-log-dir trace_log --output \
e2e_scripts/export_result/trace_log_summary.xlsx

"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

SHEET1_COLUMNS = [
    "target_paper_title",
    "target_paper_id",
    "generated_at",
    "citing_paper_count",
    "citing_context_count",
    "citing_paper_with_context_count",
    "citing_paper_no_context_count",
    "has_any_fellow",
    "citing_papers_all_agg",
    "citing_papers_fellow_agg",
]

SHEET2_COLUMNS = [
    "target_paper_title",
    "target_paper_id",
    "citing_paper_title",
    "citing_paper_venue",
    "citing_self_citation",
    "citing_has_fellow_topk",
    "citing_topk_authors_str",
    "citing_topk_authors_json",
    "reference_entry",
    "context_index",
    "context_text",
    "remark_score",
    "remark_reason",
    "row_type",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate trace_log summary.json files into an Excel workbook."
    )
    parser.add_argument(
        "--trace-log-dir",
        default="trace_log",
        help="Root directory that contains target paper folders.",
    )
    parser.add_argument(
        "--output",
        default="e2e_scripts/export_result/trace_log_summary.xlsx",
        help="Output Excel file path.",
    )
    return parser.parse_args()


def safe_list(value):
    if isinstance(value, list):
        return value
    return []


def safe_str(value, default=""):
    if value is None:
        return default
    return str(value)


def author_fellow_fields(fellow_status):
    fellow_status = fellow_status or {}
    ieee = safe_str(fellow_status.get("ieee", "Unknown"))
    acm = safe_str(fellow_status.get("acm", "Unknown"))
    aaai = safe_str(fellow_status.get("aaai", "Unknown"))
    return ieee, acm, aaai


def format_topk_authors(topk_authors, include_affiliation=False):
    parts = []
    for author in safe_list(topk_authors):
        name = safe_str(author.get("name", ""))
        h_index = safe_str(author.get("h_index", "Unknown"))
        affiliation = safe_str(author.get("affiliation", "Unknown"))
        ieee, acm, aaai = author_fellow_fields(author.get("fellow_status"))
        if include_affiliation:
            parts.append(
                f"{name}(h_index={h_index}, affiliation={affiliation}, ieee={ieee}, acm={acm}, aaai={aaai})"
            )
        else:
            parts.append(
                f"{name}(h_index={h_index}, ieee={ieee}, acm={acm}, aaai={aaai})"
            )
    return "; ".join(parts)


def format_citing_paper_agg(citing):
    title = safe_str(citing.get("paper_title", ""))
    venue = safe_str(citing.get("venue", ""))
    has_fellow = bool(citing.get("has_fellow_topk", False))
    topk_authors = format_topk_authors(citing.get("topk_authors"), include_affiliation=False)
    return (
        f"{title} | venue={venue} | fellow={has_fellow} | topk_authors=[{topk_authors}]"
    )


def load_summary(path: Path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        print(f"WARNING: failed to load {path}: {exc}", file=sys.stderr)
        return None


def find_summary_files(trace_log_dir: Path):
    if not trace_log_dir.exists():
        return []
    files = [p for p in trace_log_dir.rglob("summary.json") if p.parent.name == "res"]
    return sorted(files)


def build_rows(summary_data):
    sheet1_rows = []
    sheet2_rows = []

    for data in summary_data:
        paper_info = data.get("paper_to_analyze") or {}
        target_title = safe_str(
            paper_info.get("query_title") or paper_info.get("matched_title") or ""
        )
        target_id = safe_str(paper_info.get("paper_id", ""))
        generated_at = safe_str(data.get("generated_at", ""))

        cited_papers = safe_list(data.get("cited_paper_remarks"))

        citing_context_count = 0
        citing_paper_with_context_count = 0
        citing_paper_no_context_count = 0
        has_any_fellow = False

        agg_all = []
        agg_fellow = []

        for citing in cited_papers:
            contexts = safe_list(citing.get("contexts"))
            context_count = len(contexts)
            citing_context_count += context_count
            if context_count > 0:
                citing_paper_with_context_count += 1
            else:
                citing_paper_no_context_count += 1

            has_fellow = bool(citing.get("has_fellow_topk", False))
            if has_fellow:
                has_any_fellow = True

            agg_entry = format_citing_paper_agg(citing)
            agg_all.append(agg_entry)
            if has_fellow:
                agg_fellow.append(agg_entry)

            topk_authors = safe_list(citing.get("topk_authors"))
            topk_authors_str = format_topk_authors(
                topk_authors, include_affiliation=True
            )
            topk_authors_json = json.dumps(topk_authors, ensure_ascii=False)

            citing_title = safe_str(citing.get("paper_title", ""))
            citing_venue = safe_str(citing.get("venue", ""))
            citing_self_citation = bool(citing.get("self_citation", False))
            citing_has_fellow_topk = bool(citing.get("has_fellow_topk", False))
            reference_entry = citing.get("reference_entry")

            if contexts:
                for idx, context in enumerate(contexts):
                    context_text = context.get("context")
                    if context_text is None:
                        context_text = "None"
                    sheet2_rows.append(
                        {
                            "target_paper_title": target_title,
                            "target_paper_id": target_id,
                            "citing_paper_title": citing_title,
                            "citing_paper_venue": citing_venue,
                            "citing_self_citation": citing_self_citation,
                            "citing_has_fellow_topk": citing_has_fellow_topk,
                            "citing_topk_authors_str": topk_authors_str,
                            "citing_topk_authors_json": topk_authors_json,
                            "reference_entry": reference_entry,
                            "context_index": idx,
                            "context_text": context_text,
                            "remark_score": context.get("remark_score"),
                            "remark_reason": context.get("reason"),
                            "row_type": "has_context",
                        }
                    )
            else:
                sheet2_rows.append(
                    {
                        "target_paper_title": target_title,
                        "target_paper_id": target_id,
                        "citing_paper_title": citing_title,
                        "citing_paper_venue": citing_venue,
                        "citing_self_citation": citing_self_citation,
                        "citing_has_fellow_topk": citing_has_fellow_topk,
                        "citing_topk_authors_str": topk_authors_str,
                        "citing_topk_authors_json": topk_authors_json,
                        "reference_entry": reference_entry,
                        "context_index": 0,
                        "context_text": "None",
                        "remark_score": None,
                        "remark_reason": None,
                        "row_type": "no_context",
                    }
                )

        sheet1_rows.append(
            {
                "target_paper_title": target_title,
                "target_paper_id": target_id,
                "generated_at": generated_at,
                "citing_paper_count": len(cited_papers),
                "citing_context_count": citing_context_count,
                "citing_paper_with_context_count": citing_paper_with_context_count,
                "citing_paper_no_context_count": citing_paper_no_context_count,
                "has_any_fellow": has_any_fellow,
                "citing_papers_all_agg": "\n".join(agg_all),
                "citing_papers_fellow_agg": "\n".join(agg_fellow),
            }
        )

    return sheet1_rows, sheet2_rows


def main() -> int:
    args = parse_args()
    trace_log_dir = Path(args.trace_log_dir)
    summary_files = find_summary_files(trace_log_dir)
    if not summary_files:
        print(
            f"ERROR: no summary.json files found under {trace_log_dir}",
            file=sys.stderr,
        )
        return 1

    try:
        import openpyxl  # noqa: F401
    except ImportError:
        print(
            "ERROR: openpyxl is required to write .xlsx. Install with: pip install openpyxl",
            file=sys.stderr,
        )
        return 1

    summary_data = []
    for path in summary_files:
        data = load_summary(path)
        if data is not None:
            summary_data.append(data)

    sheet1_rows, sheet2_rows = build_rows(summary_data)
    sheet1_df = pd.DataFrame(sheet1_rows, columns=SHEET1_COLUMNS)
    sheet2_df = pd.DataFrame(sheet2_rows, columns=SHEET2_COLUMNS)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        sheet1_df.to_excel(writer, index=False, sheet_name="Sheet1")
        sheet2_df.to_excel(writer, index=False, sheet_name="Sheet2")

    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
