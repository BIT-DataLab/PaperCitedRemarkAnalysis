"""Configuration defaults for PDF fulltext extraction (Module 4)."""

from __future__ import annotations

from typing import Final, Tuple

# Public API knobs
DEFAULT_METHOD: Final[str] = "pymupdfllm"
SUPPORTED_METHODS: Final[Tuple[str, ...]] = ("pymupdf", "pymupdfllm", "mineru")

# Long-PDF truncation (to avoid slow appendix parsing)
DEFAULT_TRUNCATE_LONG_PDF: Final[bool] = True
DEFAULT_MAX_PAGES: Final[int] = 20

# pymupdf4llm backend requirements
MIN_PYMUPDF_VERSION: Final[Tuple[int, int, int]] = (1, 26, 1)

# MinerU backend defaults (MinerU runs as a local service)
DEFAULT_MINERU_URL: Final[str] = "http://localhost:18543/file_parse"
DEFAULT_MINERU_BACKEND: Final[str] = "pipeline"
DEFAULT_MINERU_LANG_LIST: Final[Tuple[str, ...]] = ("ch",)
DEFAULT_MINERU_TIMEOUT_S: Final[int] = 600
