# `pcra.get_pdf_fulltext`

Module 4: extract paper fulltext from a PDF.

## Features

- Selectable backend via `method`:
  - `pymupdfllm` (default): uses `pymupdf4llm` to produce Markdown
  - `mineru`: calls a local MinerU HTTP service
- Long PDF truncation: when `page_count > max_pages`, only parse the first `max_pages` pages.

