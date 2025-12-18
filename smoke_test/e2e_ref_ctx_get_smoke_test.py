"""Smoke test (Phase 1): cited-by -> author h-index ranking -> reference contexts.

Example:
  python3 smoke_test/e2e_ref_ctx_get_smoke_test.py \
    "Transformers over Directed Acyclic Graphs" \
    --topk-citation-cand 15 \
    --topk-author-max-h-index-cand 5 \
    --out-dir log/e2e_ref_ctx_get_run \
    --no-reuse
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pcra.pipelines import run_e2e_ref_ctx_get


def _default_out_dir() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(Path("log") / f"e2e_ref_ctx_get_{ts}")


def _maybe_int(x: Optional[str]) -> Optional[int]:
    if x is None:
        return None
    x = x.strip()
    if not x:
        return None
    return int(x)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase-1 E2E smoke test for reference-context extraction.")
    parser.add_argument("paper_to_analyze", help="Target paper title to analyze (query).")
    parser.add_argument("--topk-citation-cand", type=int, default=20, help="Top-K citing works by citation count.")
    parser.add_argument(
        "--topk-author-max-h-index-cand",
        type=int,
        default=5,
        help="Top-K citing works by max(author h-index).",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory (default: timestamped under log/).",
    )
    parser.add_argument(
        "--max-author-lookups",
        default=None,
        help="Optional cap on number of unique authors for h-index enrichment (int).",
    )
    parser.add_argument("--pdf-query-suffix", default=" pdf", help='PDF search query suffix (default: " pdf").')
    parser.add_argument("--pdf-engine", default="duckduckgo", help="PDF search engine (default: duckduckgo).")
    parser.add_argument(
        "--fulltext-method",
        default="pymupdfllm",
        help="Fulltext extraction method (default: pymupdfllm).",
    )
    parser.add_argument("--max-pages", type=int, default=20, help="Max pages used when truncating long PDFs.")
    parser.add_argument("--no-truncate", action="store_true", help="Disable long-PDF truncation.")
    parser.add_argument("--window", type=int, default=512, help="Citation context window size (chars).")
    parser.add_argument("--threshold", type=float, default=0.8, help="Reference title match threshold (0..1).")
    parser.add_argument("--no-reuse", action="store_true", help="Do not reuse existing per-paper context JSON.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    out_dir = args.out_dir or _default_out_dir()
    max_author_lookups = _maybe_int(args.max_author_lookups)

    summary = run_e2e_ref_ctx_get(
        args.paper_to_analyze,
        topk_citation_cand=args.topk_citation_cand,
        topk_author_max_h_index_cand=args.topk_author_max_h_index_cand,
        out_dir=out_dir,
        max_author_lookups=max_author_lookups,
        pdf_query_suffix=args.pdf_query_suffix,
        pdf_engine=args.pdf_engine,
        fulltext_method=args.fulltext_method,
        truncate_long_pdf=not args.no_truncate,
        max_pages=args.max_pages,
        window=args.window,
        match_threshold=args.threshold,
        reuse_existing=not args.no_reuse,
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0 if int(summary.get("context_ref_id_found") or 0) > 0 else 1)


if __name__ == "__main__":
    main()

