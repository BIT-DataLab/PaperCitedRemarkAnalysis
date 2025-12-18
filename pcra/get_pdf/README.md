# `pcra.get_pdf`

Module 3: fetch a paper PDF via a free search engine (DuckDuckGo) and download it into the repo `downloads/` directory.

## Requirements

- Selenium must be installed in your Python environment.
- Chrome & chromedriver binaries are expected at:
  - `chrome_bin/chrome-linux64/chrome`
  - `chrome_bin/chromedriver-linux64/chromedriver`

## Usage

- Library API: `pcra.get_pdf.search_and_download(query)`
- CLI smoke test:
  - `python smoke_test/get_pdf_smoke_test.py "Paper Title pdf"`

