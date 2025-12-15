"""Backend: extract PDF text via `pymupdf4llm` (Markdown output)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple
import pymupdf.layout
pymupdf.layout.activate()

from .. import config


def _parse_version(version: str) -> Tuple[int, int, int]:
    parts = []
    for token in (version or "").split("."):
        try:
            parts.append(int(token))
        except ValueError:
            break
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


def extract_markdown(
    pdf_path: Path,
    *,
    write_images: bool = False,
    image_dir: Optional[Path] = None,
) -> str:
    """Extract PDF content as Markdown via `pymupdf4llm.to_markdown`."""

    try:
        import pymupdf4llm
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Missing dependency: pymupdf4llm. Install via: pip3 install --user pymupdf4llm"
        ) from exc

    try:
        import fitz  # PyMuPDF
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Missing dependency: pymupdf (PyMuPDF). Install via: pip3 install --user 'pymupdf>=1.26.1'"
        ) from exc

    current = _parse_version(getattr(fitz, "__version__", "0.0.0"))
    if current < config.MIN_PYMUPDF_VERSION:
        need = ".".join(str(x) for x in config.MIN_PYMUPDF_VERSION)
        raise RuntimeError(
            f"Incompatible PyMuPDF version: {getattr(fitz, '__version__', 'unknown')}. "
            f"pymupdf4llm requires pymupdf>={need}."
        )

    kwargs = {}
    if write_images:
        kwargs["write_images"] = True
        if image_dir is not None:
            kwargs["image_path"] = str(image_dir)

    try:
        return pymupdf4llm.to_markdown(str(pdf_path), **kwargs)
    except AttributeError as exc:
        # Common symptom when PyMuPDF is too old for pymupdf4llm.
        need = ".".join(str(x) for x in config.MIN_PYMUPDF_VERSION)
        raise RuntimeError(
            "pymupdf4llm failed, likely due to an incompatible PyMuPDF version. "
            f"Please upgrade to pymupdf>={need}. Original error: {exc}"
        ) from exc

