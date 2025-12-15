"""DuckDuckGo HTML search (via Selenium)."""

from __future__ import annotations

import logging
from typing import List, Tuple
from urllib.parse import quote_plus

import requests
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import config
from .selenium_driver import create_chrome_driver

logger = logging.getLogger(__name__)


def search_duckduckgo(
    query: str,
    *,
    max_pages: int = config.MAX_PAGES,
    results_per_page: int = config.RESULTS_PER_PAGE,
    max_results: int = config.MAX_RESULTS,
    wait_timeout_s: int = config.SELENIUM_WAIT_TIMEOUT_S,
) -> List[Tuple[str, str]]:
    try:
        requests.get("https://duckduckgo.com", timeout=config.SEARCH_CONNECT_TIMEOUT_S)
    except Exception as exc:
        logger.warning("Network check failed for DuckDuckGo: %s", exc)
        return []

    driver = create_chrome_driver()
    try:
        links: List[Tuple[str, str]] = []
        for page_idx in range(max_pages):
            offset = page_idx * results_per_page
            search_url = (
                f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&ia=web&s={offset}"
            )
            driver.get(search_url)

            try:
                WebDriverWait(driver, wait_timeout_s).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".result__a"))
                )
            except TimeoutException:
                snippet = (driver.page_source or "")[:800]
                logger.warning(
                    "DuckDuckGo page load timeout url=%s title=%s snippet=%r",
                    driver.current_url,
                    driver.title,
                    snippet,
                )
                break

            results = driver.find_elements(By.CSS_SELECTOR, ".result__a")
            if not results:
                break

            for result in results:
                title = (result.text or "").strip()
                href = result.get_attribute("href")
                if not href:
                    continue
                links.append((title, href))
                logger.debug("DuckDuckGo result: %s -> %s", title, href)

            if len(links) >= max_results:
                links = links[:max_results]
                break

        logger.info("DuckDuckGo returned %d results", len(links))
        return links
    finally:
        driver.quit()

