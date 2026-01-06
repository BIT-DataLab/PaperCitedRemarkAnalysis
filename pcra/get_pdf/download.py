"""Download utilities for resolved PDF URLs."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from . import cache
from . import config

logger = logging.getLogger(__name__)


def safe_filename(title: str) -> str:
    return re.sub(r"[^\w.-]+", "_", (title or "").strip(), flags=re.UNICODE).strip("_")


def build_pdf_filename(paper_id: str, title: str) -> str:
    pid = safe_filename(paper_id or "")
    if not pid:
        pid = "unknown"
    name = safe_filename(title or "")
    if not name:
        name = "untitled"
    return f"{pid}_{name}.pdf"


def download_pdf(
    url: str,
    paper_id: str,
    paper_title: str,
    *,
    dest_dir: Optional[Path] = None,
    cache_path: Optional[Path] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Path:
    paper_id = (paper_id or "").strip() or "unknown"
    dest_dir = dest_dir if dest_dir is not None else config.downloads_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = build_pdf_filename(paper_id, paper_title)
    target = dest_dir / filename
    cache_path = cache_path if cache_path is not None else config.pdf_cache_path()
    base_meta: Dict[str, Any] = {
        "paper_id": paper_id,
        "paper_title": paper_title,
        "filename": filename,
        "path": str(target),
        "source_url": url,
    }
    if meta:
        base_meta.update(meta)

    if target.exists():
        base_meta["status"] = "hit"
        base_meta["size_bytes"] = target.stat().st_size
        cache.update_cache_entry(cache_path, paper_id, base_meta)
        return target

    logger.info("Downloading PDF: %s -> %s", url, target)
    with requests.get(
        url,
        headers=config.DEFAULT_HEADERS,
        stream=True,
        timeout=config.PDF_DOWNLOAD_TIMEOUT_S,
    ) as resp:
        resp.raise_for_status()
        with open(target, "wb") as fout:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    fout.write(chunk)
    base_meta["status"] = "downloaded"
    base_meta["size_bytes"] = target.stat().st_size
    cache.update_cache_entry(cache_path, paper_id, base_meta)
    return target
