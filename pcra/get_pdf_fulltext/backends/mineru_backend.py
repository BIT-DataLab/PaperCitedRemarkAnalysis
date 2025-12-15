"""Backend: extract PDF text via a local MinerU HTTP service."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from .. import config


def _extract_result_for_file(result: Dict[str, Any], pdf_path: Path) -> Dict[str, Any]:
    results = result.get("results")
    if not isinstance(results, dict):
        raise KeyError(f"MinerU response missing 'results' dict. Top-level keys: {list(result.keys())}")

    stem = pdf_path.stem
    if stem in results:
        return results[stem]

    # Some deployments may key by a different name; if only one file returned, use it.
    if len(results) == 1:
        return next(iter(results.values()))

    raise KeyError(f"MinerU response missing key for {stem!r}. Available: {list(results.keys())[:20]}")


def extract_markdown(
    pdf_path: Path,
    *,
    url: str = config.DEFAULT_MINERU_URL,
    lang_list: Optional[List[str]] = None,
    backend: str = config.DEFAULT_MINERU_BACKEND,
    timeout_s: int = config.DEFAULT_MINERU_TIMEOUT_S,
    return_images: bool = False,
    return_content_list: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    """Extract PDF content as Markdown via a local MinerU service.

    Returns:
        (md_text, backend_meta)
    """

    payload: Dict[str, Any] = {
        "output_dir": None,
        "lang_list": lang_list or list(config.DEFAULT_MINERU_LANG_LIST),
        "backend": backend,
        "parse_method": "auto",
        "formula_enable": True,
        "table_enable": True,
        "return_md": True,
        "return_middle_json": False,
        "return_model_output": False,
        "return_content_list": return_content_list,
        "return_images": return_images,
        "response_format_zip": False,
        "start_page_id": 0,
        "end_page_id": 99999,
    }

    started = time.time()
    with pdf_path.open("rb") as f:
        files = [("files", (pdf_path.name, f, "application/pdf"))]
        resp = requests.post(url, files=files, data=payload, timeout=timeout_s)

    elapsed_s = time.time() - started
    if resp.status_code != 200:
        snippet = (resp.text or "")[:500]
        raise RuntimeError(f"MinerU request failed: {resp.status_code}, {snippet}")

    try:
        result: Dict[str, Any] = resp.json()
    except json.JSONDecodeError as exc:
        snippet = (resp.text or "")[:500]
        raise RuntimeError(f"MinerU response is not valid JSON: {snippet}") from exc

    res_content = _extract_result_for_file(result, pdf_path)
    if not isinstance(res_content, dict):
        raise TypeError(f"Unexpected MinerU result type: {type(res_content)}")

    md_text = res_content.get("md_content")
    if not isinstance(md_text, str):
        raise KeyError(f"MinerU result missing 'md_content'. Keys: {list(res_content.keys())}")

    backend_meta = {
        "elapsed_s": elapsed_s,
        "result_keys": list(res_content.keys()),
    }
    return md_text, backend_meta

