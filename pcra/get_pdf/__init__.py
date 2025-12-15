"""PDF fetch utilities (Module 3: retrieve paper PDFs via free search engines).

Current implementation focuses on DuckDuckGo HTML search + Selenium rendering,
then resolves a best-matching PDF link and downloads it into the repo `downloads/`.
"""

from .facade import fetch_pdf_from_url, search_and_download

__all__ = ["fetch_pdf_from_url", "search_and_download"]

