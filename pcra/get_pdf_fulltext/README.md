# `pcra.get_pdf_fulltext`

Module 4: extract paper fulltext from a PDF.

## Features

- Selectable backend via `method`:
  - `pymupdf`: fastest; uses PyMuPDF `Page.get_text()` to return plain text (still returned as `text`)
  - `pymupdfllm` (default): uses `pymupdf4llm` to produce Markdown
  - `mineru`: calls a local MinerU HTTP service
- Long PDF truncation: when `page_count > max_pages`, only parse the first `max_pages` pages (`pymupdf` reads them directly; other backends parse a temporary truncated PDF).
