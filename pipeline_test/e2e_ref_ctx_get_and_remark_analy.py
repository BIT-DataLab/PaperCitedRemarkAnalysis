"""E2E pipeline: reference-context extraction + LLM remark analysis.

Usage:
  python3 pipeline_test/e2e_ref_ctx_get_and_remark_analy.py \
    "Human-in-the-loop Outlier Detection" \
    --topk-citation-cand 15 \
    --topk-author-max-h-index-cand 6 \
    --max-pages 30 \
    --out-dir log/e2e_ref_ctx_get_and_remark_analy_run \
    --dry-run

  python3 pipeline_test/e2e_ref_ctx_get_and_remark_analy.py \
    "Human-in-the-loop Outlier Detection" \
    --topk-citation-cand 15 \
    --topk-author-max-h-index-cand 6 \
    --max-pages 60 \
    --out-dir log/e2e_ref_ctx_get_and_remark_analy_run \
    --llm-config  ref_code/chat_llm/llm_model.yaml \
    --no-reuse


LLM config (env overrides):
  - PCRA_LLM_MODEL
  - PCRA_LLM_BASE_URL
  - PCRA_LLM_API_KEY
  - PCRA_LLM_TEMPERATURE (optional)
  - PCRA_LLM_MAX_TOKENS (optional)
  - PCRA_LLM_TIMEOUT (optional)
  - PCRA_LLM_JSON_MODE (optional)

You can also pass a YAML config with --llm-config. The default path is:
  ref_code/chat_llm/llm_model.yaml
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

from pcra.pipelines import run_e2e_ref_ctx_get_and_remark_analy


def _maybe_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return int(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase-2 E2E: ref ctx + LLM remark analysis.")
    parser.add_argument("paper_to_analyze", help="Target paper title to analyze (query).")
    parser.add_argument("--topk-citation-cand", type=int, default=15, help="Top-K citing works by citation count.")
    parser.add_argument(
        "--topk-author-max-h-index-cand",
        type=int,
        default=6,
        help="Top-K citing works by max(author h-index).",
    )
    parser.add_argument("--out-dir", default="log/e2e_ref_ctx_get_and_remark_analy_run")
    parser.add_argument("--max-author-lookups", default=None, help="Optional cap on author lookups (int).")
    parser.add_argument("--pdf-query-suffix", default=" pdf", help='PDF search query suffix (default: " pdf").')
    parser.add_argument("--pdf-engine", default="duckduckgo", help="PDF search engine (default: duckduckgo).")
    parser.add_argument(
        "--fulltext-method",
        default="pymupdfllm",
        help="Fulltext extraction method (default: pymupdfllm).",
    )
    parser.add_argument("--max-pages", type=int, default=30, help="Max pages used when truncating long PDFs.")
    parser.add_argument("--no-truncate", action="store_true", help="Disable long-PDF truncation.")
    parser.add_argument("--window", type=int, default=512, help="Citation context window size (chars).")
    parser.add_argument("--threshold", type=float, default=0.8, help="Reference title match threshold (0..1).")
    parser.add_argument("--paper-id", default=None, help="Only score this citing paper id.")
    parser.add_argument("--max-contexts", type=int, default=None, help="Limit number of contexts to score.")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls and generate mock scores.")
    parser.add_argument("--llm-config", default=None, help="Path to LLM YAML config.")
    parser.add_argument("--no-reuse", action="store_true", help="Do not reuse existing per-paper JSONs.")
    parser.add_argument("--no-skip-scored", action="store_true", help="Rescore contexts even if scored.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    max_author_lookups = _maybe_int(args.max_author_lookups)

    summary = run_e2e_ref_ctx_get_and_remark_analy(
        args.paper_to_analyze,
        topk_citation_cand=args.topk_citation_cand,
        topk_author_max_h_index_cand=args.topk_author_max_h_index_cand,
        out_dir=args.out_dir,
        max_author_lookups=max_author_lookups,
        pdf_query_suffix=args.pdf_query_suffix,
        pdf_engine=args.pdf_engine,
        fulltext_method=args.fulltext_method,
        truncate_long_pdf=not args.no_truncate,
        max_pages=args.max_pages,
        window=args.window,
        match_threshold=args.threshold,
        reuse_existing=not args.no_reuse,
        paper_id=args.paper_id,
        max_contexts=args.max_contexts,
        dry_run=args.dry_run,
        llm_config_path=args.llm_config,
        skip_scored=not args.no_skip_scored,
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
