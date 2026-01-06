"""Cache helpers for downloaded PDFs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to read pdf cache: %s", path, exc_info=True)
        return {}
    if not isinstance(payload, dict):
        logger.warning("Invalid pdf cache format: %s", path)
        return {}
    return payload


def save_cache(path: Path, cache: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(cache, ensure_ascii=True, indent=2, sort_keys=True)
    path.write_text(payload, encoding="utf-8")


def get_cached_entry(cache: Dict[str, Any], paper_id: str) -> Optional[Dict[str, Any]]:
    entry = cache.get(paper_id)
    return entry if isinstance(entry, dict) else None


def update_cache_entry(path: Path, paper_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    cache = load_cache(path)
    merged = dict(get_cached_entry(cache, paper_id) or {})
    merged.update(data)
    merged["paper_id"] = paper_id
    merged["updated_at"] = _utc_now_iso()
    cache[paper_id] = merged
    save_cache(path, cache)
    return merged
