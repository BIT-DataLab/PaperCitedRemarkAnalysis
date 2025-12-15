"""Download utilities for resolved PDF URLs."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import requests

from . import config

logger = logging.getLogger(__name__)


def safe_filename(title: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", (title or "").strip()).strip("_")
    return name or "download"


def download_pdf(url: str, title: str, *, dest_dir: Optional[Path] = None) -> Path:
    dest_dir = dest_dir if dest_dir is not None else config.downloads_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = safe_filename(title)
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    target = dest_dir / filename

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
    return target
