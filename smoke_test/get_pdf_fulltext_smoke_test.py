"""Smoke test: extract fulltext from a local PDF.

Example:
/data/QUEST/jzshe/miniconda3/envs/rag-any/bin/python smoke_test/get_pdf_fulltext_smoke_test.py \
    downloads/HippoRAG_Neurobiologically_Inspired_Long-Term_Memory_for_Large_....pdf \
    --method pymupdf --max-pages 20 --out downloads/HippoRAG_fulltext.md

或者（pymupdf4llm 输出 Markdown）
/data/QUEST/jzshe/miniconda3/envs/rag-any/bin/python smoke_test/get_pdf_fulltext_smoke_test.py \
    downloads/HippoRAG_Neurobiologically_Inspired_Long-Term_Memory_for_Large_....pdf \
    --method pymupdfllm --max-pages 20 --out downloads/HippoRAG_fulltext.md

或者
/data/QUEST/jzshe/miniconda3/envs/rag-any/bin/python smoke_test/get_pdf_fulltext_smoke_test.py \
    downloads/HippoRAG_Neurobiologically_Inspired_Long-Term_Memory_for_Large_....pdf \
     --method mineru --mineru-url http://localhost:18543/file_parse --max-pages 20 --out downloads/HippoRAG_fulltext.md

"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pcra.get_pdf_fulltext import get_pdf_fulltext


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for pcra.get_pdf_fulltext (Module 4).")
    parser.add_argument("pdf", help="Local PDF path.")
    parser.add_argument(
        "--method",
        default="pymupdfllm",
        help="Extraction method (default: pymupdfllm). Supported: pymupdf | pymupdfllm | mineru.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="Truncate when page_count > max_pages (default: 20).",
    )
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="Disable truncation and parse the full PDF.",
    )
    parser.add_argument(
        "--mineru-url",
        default="http://localhost:18543/file_parse",
        help="MinerU service URL (only for method=mineru).",
    )
    parser.add_argument("--out", default=None, help="Optional: write extracted text/Markdown to this path.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    result = get_pdf_fulltext(
        args.pdf,
        method=args.method,
        truncate_long_pdf=not args.no_truncate,
        max_pages=args.max_pages,
        mineru_url=args.mineru_url,
    )

    out_path = Path(args.out).expanduser() if args.out else None
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result["text"], encoding="utf-8")

    print(
        {
            "method": result["method"],
            "pages_used": result["pages_used"],
            "page_count": result.get("page_count"),
            "truncated": result.get("truncated"),
            "text_length": result["text_length"],
            "out": str(out_path) if out_path else None,
        }
    )


if __name__ == "__main__":
    main()
