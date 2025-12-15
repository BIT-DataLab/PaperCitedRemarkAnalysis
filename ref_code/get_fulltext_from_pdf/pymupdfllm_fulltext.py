"""Demo: extract PDF content as Markdown via PyMuPDF4LLM (pymupdf4llm).

Example:
  python3 ref_code/get_fulltext_from_pdf/pymupdf_fulltext.py \
    --pdf "/data2/jproject/PaperCitedRemarkAnalysis/downloads/HippoRAG_Neurobiologically_Inspired_Long-Term_Memory_for_Large_....pdf"
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

DEFAULT_PDF_PATH = Path(
    "/data2/jproject/PaperCitedRemarkAnalysis/downloads/"
    "HippoRAG_Neurobiologically_Inspired_Long-Term_Memory_for_Large_....pdf"
)


def pdf_to_markdown(
    pdf_path: Path,
    *,
    write_images: bool = False,
    image_dir: Optional[Path] = None,
) -> str:
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

    # pymupdf4llm currently depends on newer PyMuPDF APIs (see its PyPI requirement).
    if tuple(int(x) for x in fitz.__version__.split(".")[:3]) < (1, 26, 1):
        raise RuntimeError(
            f"Incompatible PyMuPDF version: {fitz.__version__}. "
            "pymupdf4llm requires pymupdf>=1.26.1 (you may need a newer Python)."
        )

    kwargs = {}
    if write_images:
        kwargs["write_images"] = True
        if image_dir is not None:
            kwargs["image_path"] = str(image_dir)

    return pymupdf4llm.to_markdown(str(pdf_path), **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a PDF to Markdown using pymupdf4llm.")
    parser.add_argument(
        "--pdf",
        default=str(DEFAULT_PDF_PATH),
        help=f"PDF path (default: {DEFAULT_PDF_PATH}).",
    )
    parser.add_argument("--out", default=None, help="Output Markdown path (default: <pdf>.md).")
    parser.add_argument(
        "--write-images",
        action="store_true",
        help="Extract images and reference them in Markdown.",
    )
    parser.add_argument(
        "--image-dir",
        default=None,
        help="Directory to save extracted images (default: PDF folder).",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser()
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    out_path = Path(args.out).expanduser() if args.out else pdf_path.with_suffix(".md")
    image_dir = Path(args.image_dir).expanduser() if args.image_dir else None
    if image_dir is not None:
        image_dir.mkdir(parents=True, exist_ok=True)

    md_text = pdf_to_markdown(pdf_path, write_images=args.write_images, image_dir=image_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md_text, encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
