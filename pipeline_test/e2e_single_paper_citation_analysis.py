"""CLI: single paper end-to-end citation remark analysis (refactor pipeline).

python  pipeline_test/e2e_single_paper_citation_analysis.py --paper-to-analyze "CrowdChart: Crowdsourced Data Extraction from Visualization Charts" --llm-config-path  config/llm_model.yaml  --res-dir   trace_log/CrowdChart_Crowdsourced_Data_Extraction_from_Visualization_Charts/res --log-dir trace_log/CrowdChart_Crowdsourced_Data_Extraction_from_Visualization_Charts/log  --target-author "Chengliang Chai"

python  pipeline_test/e2e_single_paper_citation_analysis.py --paper-to-analyze "GoodCore: Data-effective and Data-efficient Machine Learning through Coreset Selection over Incomplete Data" --llm-config-path  config/llm_model.yaml  --res-dir   trace_log/goodcore_data_effective_and_data_efficient_machine_learning_through_coreset_selection_over_incomplete_data/res --log-dir trace_log/goodcore_data_effective_and_data_efficient_machine_learning_through_coreset_selection_over_incomplete_data/log  --target-author "Chengliang Chai"


python  pipeline_test/e2e_single_paper_citation_analysis.py --paper-to-analyze "Database Meets Artificial Intelligence: A Survey" --llm-config-path  config/llm_model.yaml  --res-dir   trace_log/database_meets_artificial_intelligence_a_survey/res --log-dir trace_log/database_meets_artificial_intelligence_a_survey/log  --target-author "Chengliang Chai"


"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pcra.pipelines import run_e2e_single_paper


def _maybe_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return int(stripped)


def main() -> None:
    parser = argparse.ArgumentParser(description="E2E pipeline: single paper citation remark analysis.")
    parser.add_argument("--paper-to-analyze", required=True, help="Target paper title to analyze (query).")
    parser.add_argument("--target-author", default=None, help="Target author name for self-citation detection.")
    parser.add_argument("--llm-config-path", default=None, help="Path to LLM YAML config.")
    parser.add_argument("--res-dir", default="trace_log/v1_e2e_single_paper_run/res", help="Result output directory.")
    parser.add_argument("--log-dir", default="trace_log/v1_e2e_single_paper_run/log", help="Trace log output directory.")
    parser.add_argument("--cited-by-topk", type=int, default=10, help="Top-K cited-by works to keep.")
    parser.add_argument(
        "--fellow-check-topk",
        type=int,
        default=2,
        help="Top-K authors (by h-index) to check for Fellow status.",
    )
    parser.add_argument(
        "--fellow-web-search-topk",
        type=int,
        default=3,
        help="Max web search results per Fellow lookup.",
    )
    parser.add_argument(
        "--roll-back-paper-topk",
        type=int,
        default=3,
        help="Fallback Top-K papers by max h-index when no Fellow is found.",
    )
    parser.add_argument("--fulltext-method", default="mineru", help="Fulltext extraction method.") # "pymupdf", "pymupdfllm", "mineru"
    parser.add_argument("--max-pages", type=int, default=50, help="Max pages used when truncating long PDFs.")
    parser.add_argument("--window-size", type=int, default=688, help="Citation context window size (chars).")
    parser.add_argument(
        "--openalex-match-threshold",
        type=float,
        default=0.6,
        help="OpenAlex title match threshold (0..1).",
    )
    parser.add_argument(
        "--ref-ctx-match-threshold",
        type=float,
        default=0.8,
        help="Reference title match threshold (0..1).",
    )
    parser.add_argument("--max-author-lookups", default=None, help="Optional cap on author lookups (int).")
    parser.add_argument("--pdf-query-suffix", default=" pdf", help='PDF search query suffix (default: " pdf").')
    parser.add_argument("--pdf-engine", default="duckduckgo", help="PDF search engine (default: duckduckgo).")
    parser.add_argument("--max-contexts", type=int, default=None, help="Limit number of contexts to score.")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls and generate mock scores.")
    parser.add_argument("--no-skip-scored", action="store_true", help="Rescore contexts even if scored.")
    parser.add_argument("--no-truncate", action="store_true", help="Disable long-PDF truncation.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    summary = run_e2e_single_paper(
        args.paper_to_analyze,
        target_author=args.target_author,
        llm_config_path=args.llm_config_path,
        res_dir=args.res_dir,
        log_dir=args.log_dir,
        cited_by_topK=args.cited_by_topk,
        fellow_check_topK=args.fellow_check_topk,
        fellow_web_search_topk=args.fellow_web_search_topk,
        roll_back_paper_topK=args.roll_back_paper_topk,
        openalex_match_threshold=args.openalex_match_threshold,
        ref_ctx_match_threshold=args.ref_ctx_match_threshold,
        window_size=args.window_size,
        pdf_query_suffix=args.pdf_query_suffix,
        pdf_engine=args.pdf_engine,
        fulltext_method=args.fulltext_method,
        truncate_long_pdf=not args.no_truncate,
        max_pages=args.max_pages,
        max_author_lookups=_maybe_int(args.max_author_lookups),
        max_contexts=args.max_contexts,
        dry_run=args.dry_run,
        skip_scored=not args.no_skip_scored,
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
