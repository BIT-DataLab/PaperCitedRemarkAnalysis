"""Configuration defaults for PDF fetching."""

from __future__ import annotations

from pathlib import Path

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
}

STOP_TOKENS = {"pdf", "paper", "arxiv", "openreview", "ieee", "proceedings", "www", "http", "https"}

# Match / filtering knobs
MIN_TITLE_HITS = 3
MIN_TITLE_OVERLAP = 0.6
MIN_PDF_SCORE = 3

# DuckDuckGo search knobs
RESULTS_PER_PAGE = 30  # DuckDuckGo HTML default page size
MAX_PAGES = 3
MAX_RESULTS = 100

# HTTP / Selenium timeouts
SEARCH_CONNECT_TIMEOUT_S = 5
PAGE_FETCH_TIMEOUT_S = 20
PDF_DOWNLOAD_TIMEOUT_S = 30
SELENIUM_WAIT_TIMEOUT_S = 10

# Repo-relative paths (requested by user: no hard-coded absolute paths)
CHROME_BINARY_REL_PATH = Path("chrome_bin") / "chrome-linux64" / "chrome"
CHROMEDRIVER_REL_PATH = Path("chrome_bin") / "chromedriver-linux64" / "chromedriver"
CHROMEDRIVER_LOG_REL_PATH = Path("log") / "chromedriver.log"
DOWNLOADS_REL_DIR = Path("downloads")


def repo_root() -> Path:
    # pcra/get_pdf/config.py -> parents: get_pdf -> pcra -> repo_root
    return Path(__file__).resolve().parents[2]


def chrome_binary_path() -> Path:
    return repo_root() / CHROME_BINARY_REL_PATH


def chromedriver_path() -> Path:
    return repo_root() / CHROMEDRIVER_REL_PATH


def chromedriver_log_path() -> Path:
    return repo_root() / CHROMEDRIVER_LOG_REL_PATH


def downloads_dir() -> Path:
    return repo_root() / DOWNLOADS_REL_DIR

