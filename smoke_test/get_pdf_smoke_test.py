"""Smoke test: download a paper PDF via DuckDuckGo + Selenium.

Example:
  /data/QUEST/jzshe/miniconda3/envs/tracer/bin/python tools/get_pdf_smoke_test.py \
    "Rethink GraphODE Generalization within Coupled Dynamical System pdf"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pcra.get_pdf import fetch_pdf_from_url, search_and_download


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for pcra.get_pdf (Module 3).")
    parser.add_argument("query", help="Search query (usually: paper title + 'pdf').")
    parser.add_argument("--engine", default="duckduckgo", help="Search engine (default: duckduckgo).")
    parser.add_argument(
        "--url",
        default=None,
        help="Optional: directly resolve & download PDF from a page URL (skips search).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.url:
        path = fetch_pdf_from_url(args.url, args.query)
    else:
        path = search_and_download(args.query, engine=args.engine)

    print(path)
    raise SystemExit(0 if path else 1)


if __name__ == "__main__":
    main()

