"""DuckDuckGo-based paper PDF downloader (reference script).

This file keeps a stable top-level function `search_and_download` but delegates the
core implementation to `pcra.get_pdf`.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pcra.get_pdf import fetch_pdf_from_url as _fetch_pdf_from_url
from pcra.get_pdf import search_and_download as _search_and_download


def search_and_download(query: str, engine: str = "duckduckgo") -> Optional[Path]:
    return _search_and_download(query, engine=engine)


def fetch_pdf_from_url(url: str, query: str) -> Optional[Path]:
    return _fetch_pdf_from_url(url, query)


def _demo() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    query = "Rethink GraphODE Generalization within Coupled Dynamical System pdf"
    path = search_and_download(query, engine="duckduckgo")
    print(path)


if __name__ == "__main__":
    _demo()
