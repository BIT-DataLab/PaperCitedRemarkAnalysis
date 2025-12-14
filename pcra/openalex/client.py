"""OpenAlex HTTP client (mailto/user-agent/retry/cursor paging)."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterator, Optional

import requests

DEFAULT_BASE_URL = "https://api.openalex.org"


class OpenAlexClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        mailto: Optional[str] = None,
        user_agent: Optional[str] = None,
        timeout_s: int = 30,
        max_retries: int = 3,
        backoff_s: float = 1.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.mailto = (
            mailto
            if mailto is not None
            else os.environ.get("OPENALEX_MAILTO", "1165324684@qq.com")
        )
        self.user_agent = (
            user_agent
            if user_agent is not None
            else os.environ.get("OPENALEX_USER_AGENT", "pcra-openalex/0.1")
        )
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.session = session or requests.Session()

    def _make_url(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        if not path_or_url.startswith("/"):
            path_or_url = "/" + path_or_url
        return self.base_url + path_or_url

    def _with_mailto(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = dict(params or {})
        if self.mailto:
            merged.setdefault("mailto", self.mailto)
        return merged

    def get_json(
        self,
        path_or_url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = self._make_url(path_or_url)
        merged_headers = dict(headers or {})
        merged_headers.setdefault("User-Agent", self.user_agent)
        merged_params = self._with_mailto(params)

        attempt = 0
        while True:
            resp = self.session.get(
                url, params=merged_params, headers=merged_headers, timeout=self.timeout_s
            )
            if resp.ok:
                return resp.json()

            attempt += 1
            retriable = resp.status_code in {429, 500, 502, 503, 504}
            if (not retriable) or attempt > self.max_retries:
                raise RuntimeError(
                    f"OpenAlex request failed {resp.status_code} for {resp.url}: {resp.text[:200]}"
                )

            retry_after = resp.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                sleep_s = float(retry_after)
            else:
                sleep_s = self.backoff_s * (2 ** (attempt - 1))
            time.sleep(sleep_s)

    def iter_cursor(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        per_page: int = 200,
        cursor: str = "*",
        max_pages: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Iterate list endpoints using OpenAlex cursor paging."""
        cur = cursor
        page = 0
        while True:
            page += 1
            if max_pages is not None and page > max_pages:
                return
            req_params = dict(params or {})
            req_params["per-page"] = per_page
            req_params["cursor"] = cur
            data = self.get_json(path, params=req_params)
            results = data.get("results") or []
            for item in results:
                yield item
            next_cursor = (data.get("meta") or {}).get("next_cursor")
            if not next_cursor or not results:
                return
            cur = next_cursor

