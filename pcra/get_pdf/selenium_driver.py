"""Selenium Chrome driver factory for fetching search results."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from . import config


def create_chrome_driver(
    *,
    chrome_binary: Optional[Path] = None,
    chromedriver_binary: Optional[Path] = None,
    chromedriver_log: Optional[Path] = None,
    user_agent: str = config.DEFAULT_USER_AGENT,
    headless: bool = True,
) -> webdriver.Chrome:
    chrome_binary = chrome_binary if chrome_binary is not None else config.chrome_binary_path()
    chromedriver_binary = (
        chromedriver_binary if chromedriver_binary is not None else config.chromedriver_path()
    )
    chromedriver_log = chromedriver_log if chromedriver_log is not None else config.chromedriver_log_path()

    if not chrome_binary.exists():
        raise FileNotFoundError(
            f"Chrome binary not found: {chrome_binary} (expected relative {config.CHROME_BINARY_REL_PATH})"
        )
    if not chromedriver_binary.exists():
        raise FileNotFoundError(
            f"Chromedriver binary not found: {chromedriver_binary} (expected relative {config.CHROMEDRIVER_REL_PATH})"
        )

    options = Options()
    options.binary_location = str(chrome_binary)
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--user-agent={user_agent}")

    chromedriver_log.parent.mkdir(parents=True, exist_ok=True)
    service = Service(executable_path=str(chromedriver_binary), log_path=str(chromedriver_log))
    return webdriver.Chrome(service=service, options=options)

