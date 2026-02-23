"""Fellow lookup via local web extraction or OpenRouter web search."""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

import requests

PROMPT_HONOR_CHECK = """You are performing a precise honor verification task for a scholar.

Given the following information:
- Scholar name: {name}
- Affiliation: {affiliation}
- Paper institutions: {paper_institutions}

Please check separately whether this scholar has been awarded the following honors:
- IEEE Fellow
- ACM Fellow
- AAAI Fellow

For each organization, report:
- Award status: Yes / No / Unknown
- Year of award (if available)
- Source of information (personal homepage or Wikipedia only)

Do NOT infer or guess.
If no reliable evidence is found, mark the status as Unknown.
Return results in a structured, per-organization format.

STRICT CONSTRAINTS:

1. Allowed sources ONLY:
   - The scholar's personal homepage (lab/university page with their bio/CV).
   - Wikipedia page about the scholar.
2. Disallowed sources:
   - ACM/IEEE/AAAI sites, award lists, announcements, conference pages, or other org sites.
3. Evidence limit: use at most ONE reliable source per organization.
4. Search budget: shallow search only; if evidence is not found quickly, return "Unknown".
5. Output format (must follow exactly):

IEEE Fellow: Yes | No | Unknown
Year: <year or N/A>
Source: <single URL or N/A>

ACM Fellow: Yes | No | Unknown
Year: <year or N/A>
Source: <single URL or N/A>

AAAI Fellow: Yes | No | Unknown
Year: <year or N/A>
Source: <single URL or N/A>
"""

PROMPT_LOCAL_PAGE_HONOR_CHECK = """You verify fellowship honors using ONLY the provided page excerpt.

You are given:
- Target scholar identity (name / affiliation / paper institutions)
- One webpage URL
- One markdown excerpt extracted from that same webpage

Rules:
1. Use ONLY the excerpt. Do not use prior knowledge.
2. First decide whether this page is about the target scholar (`is_target_scholar`).
3. Decide whether the excerpt contains valid profile/bio content (`has_valid_profile_content`):
   - valid if it is a scholar bio/profile style page (position, institution, research, education, honors, CV-like sections)
   - invalid for nav pages, lists, announcements, unrelated pages.
4. For each honor (IEEE Fellow / ACM Fellow / AAAI Fellow):
   - `Yes` only if explicit evidence says the target scholar is that Fellow.
   - `No` only if explicit evidence says the target scholar is NOT that Fellow.
   - otherwise `Unknown`.
5. If either `is_target_scholar` is false OR `has_valid_profile_content` is false, set all honor statuses to `Unknown`.
6. Return JSON only. No extra text.

Required JSON schema:
{
  "is_target_scholar": true/false,
  "has_valid_profile_content": true/false,
  "fellow": {
    "IEEE Fellow": {"status": "Yes|No|Unknown", "year": "<year or N/A>"},
    "ACM Fellow": {"status": "Yes|No|Unknown", "year": "<year or N/A>"},
    "AAAI Fellow": {"status": "Yes|No|Unknown", "year": "<year or N/A>"}
  }
}
"""

HONOR_ORGS = ("IEEE Fellow", "ACM Fellow", "AAAI Fellow")
ORG_TO_KEY = {
    "IEEE Fellow": "ieee",
    "ACM Fellow": "acm",
    "AAAI Fellow": "aaai",
}
KEY_TO_ORG = {v: k for k, v in ORG_TO_KEY.items()}

PLACEHOLDER_API_KEYS = {"", "YOUR_OPENROUTER_API_KEY", "OPENROUTER_API_KEY", "REPLACE_ME"}
CACHE_TTL_DAYS = 180
CACHE_VERSION = 2

DEFAULT_FELLOW_MODE = "local_only"
FELLOW_MODES = {"local_only", "local_with_fallback", "openrouter_only"}

BLOCKED_HOST_KEYWORDS = (
    "ieee.org",
    "acm.org",
    "aaai.org",
    "dblp.org",
    "openreview.net",
    "arxiv.org",
    "scholar.google.",
)
PROFILE_URL_HINTS = (
    "faculty",
    "people",
    "person",
    "profile",
    "homepage",
    "home",
    "bio",
    "about",
    "cv",
    "staff",
)
PROFILE_TITLE_HINTS = (
    "prof",
    "professor",
    "faculty",
    "bio",
    "homepage",
    "curriculum vitae",
    "research",
    "staff",
)

EXTRACT_MODES = {"auto", "trafilatura_html", "trafilatura_txt", "bs4_body", "keyword_window"}

RULE_POSITIVE_PATTERNS: Tuple[Tuple[re.Pattern[str], Tuple[str, ...], str], ...] = (
    (re.compile(r"\bacm\s*/\s*ieee\s*fellow(?:s)?\b", re.IGNORECASE), ("ACM Fellow", "IEEE Fellow"), "slash"),
    (
        re.compile(r"\bhe\s+was\s+acm\s+fellow\s+and\s+ieee\s+fellow\b", re.IGNORECASE),
        ("ACM Fellow", "IEEE Fellow"),
        "sentence",
    ),
    (re.compile(r"\bacm\s+fellow\b", re.IGNORECASE), ("ACM Fellow",), "single"),
    (re.compile(r"\bieee\s+fellow\b", re.IGNORECASE), ("IEEE Fellow",), "single"),
    (re.compile(r"\baaai\s+fellow\b", re.IGNORECASE), ("AAAI Fellow",), "single"),
)

RULE_NEGATIVE_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bnot\s+(?:an?\s+)?acm\s+fellow\b", re.IGNORECASE), "ACM Fellow"),
    (re.compile(r"\bnot\s+(?:an?\s+)?ieee\s+fellow\b", re.IGNORECASE), "IEEE Fellow"),
    (re.compile(r"\bnot\s+(?:an?\s+)?aaai\s+fellow\b", re.IGNORECASE), "AAAI Fellow"),
)

EXTRACTION_HINT_KEYWORDS = (
    "biography",
    "acm fellow",
    "ieee fellow",
    "aaai fellow",
    "professor",
    "research interests",
)

logger = logging.getLogger(__name__)


def _load_minimal_yaml(path: Path) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    cur_section: Optional[str] = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not raw_line.startswith((" ", "\t")) and line.endswith(":"):
            cur_section = line[:-1].strip()
            data[cur_section] = {}
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
            value = value[1:-1]
        if cur_section is None:
            data[key] = value
        else:
            section_obj = data.get(cur_section)
            if isinstance(section_obj, dict):
                section_obj[key] = value
            else:
                data[cur_section] = {key: value}
    return data


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        return _load_minimal_yaml(path)

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML root type: {type(data)!r}")
    return data


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit() or (stripped.startswith("-") and stripped[1:].isdigit()):
            return int(stripped)
    return default


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return default


def _normalize_status(value: Any) -> str:
    if not isinstance(value, str):
        return "Unknown"
    lowered = value.strip().lower()
    if lowered == "yes":
        return "Yes"
    if lowered == "no":
        return "No"
    return "Unknown"


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.strip().lower())


def _normalize_markdown(markdown: str, char_limit: int) -> str:
    if not isinstance(markdown, str):
        return ""
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if len(text) > char_limit:
        text = text[:char_limit]
    return text


def _plain_text_to_markdown(text: str, *, char_limit: int) -> str:
    if not text:
        return ""
    lines = [ln.strip() for ln in text.splitlines()]
    paragraphs: List[str] = []
    buf: List[str] = []
    for ln in lines:
        if not ln:
            if buf:
                paragraphs.append(" ".join(buf))
                buf = []
            continue
        buf.append(ln)
    if buf:
        paragraphs.append(" ".join(buf))
    markdown = "\n\n".join(paragraphs)
    return _normalize_markdown(markdown, char_limit)


def _hostname(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _path_depth(url: str) -> int:
    path = urlsplit(url).path or ""
    return len([seg for seg in path.split("/") if seg])


def _url_has_profile_hint(url: str, title: str) -> bool:
    lowered_url = (url or "").lower()
    lowered_title = (title or "").lower()
    return any(hint in lowered_url for hint in PROFILE_URL_HINTS) or any(
        hint in lowered_title for hint in PROFILE_TITLE_HINTS
    )


def _is_personal_homepage_like(url: str, title: str, name_tokens: Sequence[str]) -> bool:
    host = _hostname(url)
    path = urlsplit(url).path or ""
    depth = _path_depth(url)
    lowered_url = (url or "").lower()
    lowered_title = (title or "").lower()
    token_hits = sum(tok in lowered_url or tok in lowered_title for tok in name_tokens)

    if "/~" in path or path.endswith("/~") or re.search(r"/~[a-z0-9._-]+/?$", path, re.IGNORECASE):
        return True
    if depth <= 2 and token_hits >= 1 and (".edu" in host or "cs." in host):
        return True
    if _url_has_profile_hint(url, title) and token_hits >= 1:
        return True
    return False


def _extract_urls(text: str) -> List[str]:
    if not text:
        return []
    return re.findall(r"https?://[^\s)\]>\"']+", text, flags=re.IGNORECASE)


def _parse_json_from_text(text: str) -> Dict[str, Any]:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        snippet = text[start : end + 1]
        data = json.loads(snippet)
        if isinstance(data, dict):
            return data
    raise ValueError("JSON parse failed")


def _format_institutions(items: Optional[Iterable[Any]]) -> str:
    if not items:
        return ""
    parts: List[str] = []
    for inst in items:
        if isinstance(inst, str):
            name = inst.strip()
            if name:
                parts.append(name)
            continue
        if not isinstance(inst, dict):
            continue
        name = inst.get("display_name") or inst.get("name")
        ror = inst.get("ror")
        country = inst.get("country_code")
        segments = [
            seg
            for seg in [
                name,
                f"ror={ror}" if ror else None,
                f"country={country}" if country else None,
            ]
            if seg
        ]
        if segments:
            parts.append(" | ".join(segments))
    return "; ".join(parts)


def _dedupe_urls(urls: Iterable[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for url in urls:
        if not isinstance(url, str):
            continue
        stripped = url.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        deduped.append(stripped)
    return deduped


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate_text(text: str, limit: int = 1200) -> str:
    if not isinstance(text, str):
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def _safe_slug(value: str, default: str = "unknown") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    cleaned = cleaned.strip("_.-")
    if cleaned:
        return cleaned[:80]
    return default


def _mask_api_key(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _settings_for_debug(settings: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(settings, Mapping):
        return {}
    out: Dict[str, Any] = {}
    for key, value in settings.items():
        key_s = str(key)
        if key_s.lower() in {"api_key"}:
            out[key_s] = _mask_api_key(value)
            continue
        out[key_s] = value
    return out


def _write_debug_payload(debug_dir: Path, payload: Mapping[str, Any]) -> Optional[str]:
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        scholar = _safe_slug(str((payload.get("input") or {}).get("name") or "scholar"))
        nonce_src = json.dumps(
            {
                "name": (payload.get("input") or {}).get("name"),
                "ts": payload.get("started_at"),
                "mode": payload.get("mode"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
        suffix = sha1(nonce_src.encode("utf-8")).hexdigest()[:8]
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = debug_dir / f"{ts}_{scholar}_{suffix}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return str(path)
    except Exception:  # noqa: BLE001
        return None


def _finalize_lookup_result(
    *,
    statuses: Mapping[str, str],
    sources: Iterable[str],
    error: Optional[str],
    debug: Optional[Dict[str, Any]],
    debug_dir: Optional[Path],
) -> Tuple[Dict[str, str], List[str], Optional[str]]:
    normalized = {
        "ieee": _normalize_status(statuses.get("ieee")),
        "acm": _normalize_status(statuses.get("acm")),
        "aaai": _normalize_status(statuses.get("aaai")),
    }
    deduped_sources = _dedupe_urls(sources)

    if debug is not None:
        debug["finished_at"] = _utc_now_iso()
        debug["result"] = {
            "statuses": normalized,
            "sources_count": len(deduped_sources),
            "sources": deduped_sources,
            "error": error,
        }
        if debug_dir is not None:
            debug_path = _write_debug_payload(debug_dir, debug)
            if debug_path:
                debug["debug_path"] = debug_path
                # Append path to error string only when there is already an error,
                # so normal callers keep legacy behavior.
                if error:
                    error = f"{error} | debug={debug_path}"

    return normalized, deduped_sources, error


def _default_statuses() -> Dict[str, str]:
    return {"ieee": "Unknown", "acm": "Unknown", "aaai": "Unknown"}


def _all_unknown(statuses: Mapping[str, str]) -> bool:
    return all(str(statuses.get(k) or "Unknown") == "Unknown" for k in ("ieee", "acm", "aaai"))


def _statuses_to_org_map(statuses: Mapping[str, str]) -> Dict[str, str]:
    result = {org: "Unknown" for org in HONOR_ORGS}
    for key, value in statuses.items():
        org = KEY_TO_ORG.get(key)
        if org:
            result[org] = _normalize_status(value)
    return result


def _statuses_from_org_map(statuses: Mapping[str, Any]) -> Dict[str, str]:
    result = _default_statuses()
    for org in HONOR_ORGS:
        key = ORG_TO_KEY[org]
        result[key] = _normalize_status(statuses.get(org))
    return result


def _normalize_cached_statuses(statuses: Any) -> Dict[str, str]:
    if not isinstance(statuses, dict):
        return _default_statuses()
    if any(k in statuses for k in ("ieee", "acm", "aaai")):
        return {
            "ieee": _normalize_status(statuses.get("ieee")),
            "acm": _normalize_status(statuses.get("acm")),
            "aaai": _normalize_status(statuses.get("aaai")),
        }
    return _statuses_from_org_map(statuses)


def _load_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"version": CACHE_VERSION, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": CACHE_VERSION, "entries": {}}
    if not isinstance(data, dict):
        return {"version": CACHE_VERSION, "entries": {}}
    if data.get("version") != CACHE_VERSION or not isinstance(data.get("entries"), dict):
        return {"version": CACHE_VERSION, "entries": {}}
    return data


def _save_cache(path: Path, cache: Mapping[str, Any]) -> None:
    payload = json.dumps(cache, ensure_ascii=True, indent=2, sort_keys=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(path)


def _get_cached(cache: Mapping[str, Any], key: str) -> Optional[Dict[str, Any]]:
    entries = cache.get("entries")
    if not isinstance(entries, dict):
        return None
    entry = entries.get(key)
    if not isinstance(entry, dict):
        return None
    timestamp = entry.get("timestamp")
    if not isinstance(timestamp, (int, float)):
        return None
    ttl_seconds = CACHE_TTL_DAYS * 24 * 60 * 60
    if time.time() - float(timestamp) > ttl_seconds:
        return None
    return entry


def _store_cache(
    cache: Dict[str, Any],
    key: str,
    statuses: Mapping[str, str],
    sources: List[str],
    raw_text: str,
) -> None:
    entries = cache.setdefault("entries", {})
    if not isinstance(entries, dict):
        cache["entries"] = {}
        entries = cache["entries"]
    entries[key] = {
        "timestamp": time.time(),
        "statuses": {
            "ieee": _normalize_status(statuses.get("ieee")),
            "acm": _normalize_status(statuses.get("acm")),
            "aaai": _normalize_status(statuses.get("aaai")),
        },
        "sources": list(sources),
        "raw_text": raw_text,
    }


def _make_cache_key(
    name: str,
    affiliation: str,
    paper_institutions: str,
    cache_settings: Mapping[str, Any],
) -> str:
    parts = {
        "name": _normalize_text(name),
        "affiliation": _normalize_text(affiliation),
        "institutions": _normalize_text(paper_institutions),
        "mode": str(cache_settings.get("mode") or DEFAULT_FELLOW_MODE),
        "max_results": int(cache_settings.get("max_results") or 0),
        "allow_wikipedia": bool(cache_settings.get("allow_wikipedia")),
        "profile_char_limit": int(cache_settings.get("profile_char_limit") or 0),
        "extract_markdown_mode": str(cache_settings.get("extract_markdown_mode") or "auto"),
        "rule_assisted_honor_detection": bool(cache_settings.get("rule_assisted_honor_detection")),
        "local_model": str(cache_settings.get("local_model") or ""),
        "openrouter_model": str(cache_settings.get("openrouter_model") or ""),
    }
    return json.dumps(parts, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _read_text_llm_settings(
    config: Mapping[str, Any],
    timeout_override: Optional[int],
    max_retries_override: Optional[int],
) -> Dict[str, Any]:
    text_cfg = config.get("text")
    if isinstance(text_cfg, dict) and text_cfg:
        section = text_cfg
    else:
        raise ValueError("Missing 'text' section in config")

    model = os.getenv("PCRA_LLM_MODEL") or section.get("model")
    api_base = os.getenv("PCRA_LLM_BASE_URL") or section.get("api_base") or section.get("base_url")
    api_key = os.getenv("PCRA_LLM_API_KEY") or section.get("api_key")

    if not model:
        raise ValueError("Missing text.model in config")
    if not api_base:
        raise ValueError("Missing text.api_base/text.base_url in config")
    if not api_key:
        raise ValueError("Missing text.api_key in config")

    timeout_s = _coerce_int(section.get("timeout_s") or section.get("timeout"), default=60)
    max_retries = _coerce_int(section.get("max_retries"), default=2)
    max_tokens = _coerce_int(section.get("max_tokens"), default=512)
    if timeout_override is not None:
        timeout_s = max(1, int(timeout_override))
    if max_retries_override is not None:
        max_retries = max(0, int(max_retries_override))

    return {
        "model": str(model),
        "api_base": str(api_base).rstrip("/"),
        "api_key": str(api_key),
        "timeout_s": timeout_s,
        "max_retries": max_retries,
        "max_tokens": max(128, max_tokens),
    }


def _read_openrouter_settings(
    config: Mapping[str, Any],
    max_results_override: Optional[int],
    timeout_override: Optional[int],
    max_retries_override: Optional[int],
) -> Dict[str, Any]:
    section = config.get("openrouter_web_search")
    if not isinstance(section, dict):
        raise ValueError("Missing 'openrouter_web_search' section in config")

    model = section.get("model")
    api_base = section.get("api_base") or section.get("base_url") or "https://openrouter.ai/api/v1"
    api_key = section.get("api_key")
    api_key_env = section.get("api_key_env") or "OPENROUTER_API_KEY"

    if isinstance(api_key, str) and api_key.strip() in PLACEHOLDER_API_KEYS:
        api_key = None
    if not api_key and isinstance(api_key_env, str):
        env_value = os.getenv(api_key_env)
        if env_value:
            api_key = env_value

    if not model:
        raise ValueError("Missing openrouter_web_search.model in config")
    if not api_key:
        raise ValueError("Missing OpenRouter API key; set openrouter_web_search.api_key or env")

    web_search_mode = section.get("web_search_mode") or "plugins"
    if isinstance(web_search_mode, str):
        web_search_mode = web_search_mode.strip().lower()
    if web_search_mode not in ("plugins", "online"):
        raise ValueError("web_search_mode must be 'plugins' or 'online'")

    max_results = _coerce_int(section.get("max_results"), default=5)
    if max_results_override is not None:
        max_results = max(1, int(max_results_override))
    timeout_s = _coerce_int(section.get("timeout_s"), default=60)
    max_retries = _coerce_int(section.get("max_retries"), default=2)
    if timeout_override is not None:
        timeout_s = max(1, int(timeout_override))
    if max_retries_override is not None:
        max_retries = max(0, int(max_retries_override))

    return {
        "model": str(model),
        "api_base": str(api_base).rstrip("/"),
        "api_key": str(api_key),
        "web_search_mode": web_search_mode,
        "max_results": max_results,
        "timeout_s": timeout_s,
        "max_retries": max_retries,
    }


def _read_fellow_lookup_settings(
    config: Mapping[str, Any],
    max_results_override: Optional[int],
    timeout_override: Optional[int],
    max_retries_override: Optional[int],
) -> Dict[str, Any]:
    section = config.get("fellow_lookup")
    if not isinstance(section, dict):
        section = {}

    mode = str(section.get("mode") or DEFAULT_FELLOW_MODE).strip().lower()
    if mode not in FELLOW_MODES:
        raise ValueError(f"Invalid fellow_lookup.mode: {mode}")

    max_results = _coerce_int(section.get("max_results"), default=5)
    if max_results_override is not None:
        max_results = max(1, int(max_results_override))

    timeout_s = _coerce_int(section.get("timeout_s"), default=60)
    if timeout_override is not None:
        timeout_s = max(1, int(timeout_override))

    max_retries = _coerce_int(section.get("max_retries"), default=2)
    if max_retries_override is not None:
        max_retries = max(0, int(max_retries_override))

    profile_char_limit = _coerce_int(section.get("profile_char_limit"), default=8000)
    min_profile_chars = _coerce_int(section.get("min_profile_chars"), default=200)
    dynamic_wait_s = _coerce_int(section.get("dynamic_wait_s"), default=8)
    debug_markdown_max_chars = _coerce_int(section.get("debug_markdown_max_chars"), default=20000)
    extract_markdown_mode = str(section.get("extract_markdown_mode") or "auto").strip().lower()
    if extract_markdown_mode not in EXTRACT_MODES:
        extract_markdown_mode = "auto"

    return {
        "mode": mode,
        "allow_wikipedia": _coerce_bool(section.get("allow_wikipedia"), default=True),
        "max_results": max(1, max_results),
        "timeout_s": timeout_s,
        "max_retries": max_retries,
        "profile_char_limit": max(512, profile_char_limit),
        "min_profile_chars": max(1, min_profile_chars),
        "dynamic_wait_s": max(1, dynamic_wait_s),
        "extract_markdown_mode": extract_markdown_mode,
        "debug_markdown_max_chars": max(2000, debug_markdown_max_chars),
        "rule_assisted_honor_detection": _coerce_bool(
            section.get("rule_assisted_honor_detection"),
            default=True,
        ),
    }


def _http_post_json(
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
    timeout_s: int,
    max_retries: int,
) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    last_err: Optional[BaseException] = None
    attempts = max(1, int(max_retries) + 1)
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, data=data, headers=dict(headers), method="POST")
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_err = RuntimeError(f"HTTP {exc.code}: {body or exc.reason}")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        if attempt < attempts - 1:
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"HTTP request failed after retries: {last_err}")


def _call_openrouter_chat(prompt: str, settings: Mapping[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    model = str(settings["model"])
    if settings["web_search_mode"] == "online" and not model.endswith(":online"):
        model = f"{model}:online"

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if settings["web_search_mode"] == "plugins":
        payload["plugins"] = [{"id": "web", "max_results": settings["max_results"]}]

    url = f"{settings['api_base']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
        "User-Agent": "PaperCitedRemarkAnalysis/OpenRouterWebSearch",
    }
    response = _http_post_json(
        url=url,
        headers=headers,
        payload=payload,
        timeout_s=int(settings["timeout_s"]),
        max_retries=int(settings["max_retries"]),
    )
    if isinstance(response, dict) and response.get("error"):
        raise RuntimeError(f"OpenRouter error: {response['error']}")

    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("OpenRouter response missing choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise RuntimeError("OpenRouter response missing message")

    content = message.get("content")
    annotations = message.get("annotations")
    if not isinstance(content, str):
        content = ""
    if not isinstance(annotations, list):
        annotations = []
    return content, [a for a in annotations if isinstance(a, dict)]


def _parse_honor_statuses(text: str) -> Dict[str, Optional[str]]:
    statuses: Dict[str, Optional[str]] = {}
    for org in HONOR_ORGS:
        status: Optional[str] = None
        for line in text.splitlines():
            if org.lower() in line.lower():
                match = re.search(r"\b(Yes|No|Unknown)\b", line, re.IGNORECASE)
                if match:
                    status = match.group(1).capitalize()
                    break
        if status is None:
            match = re.search(
                rf"{re.escape(org)}.*?\b(Yes|No|Unknown)\b",
                text,
                re.IGNORECASE | re.DOTALL,
            )
            if match:
                status = match.group(1).capitalize()
        statuses[org] = status
    return statuses


def _collect_citations(annotations: Iterable[Mapping[str, Any]]) -> List[str]:
    urls: List[str] = []
    for ann in annotations:
        if ann.get("type") != "url_citation":
            continue
        citation = ann.get("url_citation") or {}
        if not isinstance(citation, dict):
            continue
        url = citation.get("url")
        if isinstance(url, str) and url:
            urls.append(url)
    return urls


def _collect_urls_from_text(text: str) -> List[str]:
    return re.findall(r"https?://\S+", text or "")


def _lookup_via_openrouter(
    name: str,
    affiliation: str,
    paper_institutions: str,
    openrouter_settings: Mapping[str, Any],
    *,
    debug: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, str], List[str], str, Optional[str]]:
    if debug is not None:
        debug["settings"] = _settings_for_debug(openrouter_settings)

    prompt = PROMPT_HONOR_CHECK.format(
        name=name,
        affiliation=affiliation or "Unknown",
        paper_institutions=paper_institutions or "Unknown",
    )
    if debug is not None:
        debug["prompt_preview"] = _truncate_text(prompt, limit=2000)

    try:
        content, annotations = _call_openrouter_chat(prompt, openrouter_settings)
    except Exception as exc:  # noqa: BLE001
        if debug is not None:
            debug["error"] = f"{type(exc).__name__}: {exc}"
        return _default_statuses(), [], "", f"{type(exc).__name__}: {exc}"

    raw_statuses = _parse_honor_statuses(content)
    statuses = _statuses_from_org_map(raw_statuses)

    sources = _collect_citations(annotations)
    if not sources:
        sources = _collect_urls_from_text(content)
    deduped_sources = _dedupe_urls(sources)
    if debug is not None:
        debug["raw_statuses"] = raw_statuses
        debug["statuses"] = statuses
        debug["sources"] = deduped_sources
        debug["content_preview"] = _truncate_text(content, limit=2400)
        debug["annotations_count"] = len(list(annotations))

    return statuses, deduped_sources, content, None


def _normalize_candidate_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l"):
        query = parse_qs(parsed.query)
        uddg = query.get("uddg")
        if uddg and isinstance(uddg[0], str):
            return _normalize_candidate_url(unquote(uddg[0]))

    cleaned = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
    return cleaned.strip()


def _is_wikipedia_url(url: str) -> bool:
    host = (urlsplit(url).netloc or "").lower()
    return host.endswith("wikipedia.org")


def _looks_like_blocked_source(url: str) -> bool:
    lowered = url.lower()
    if lowered.split("?", 1)[0].endswith(".pdf"):
        return True
    return any(token in lowered for token in BLOCKED_HOST_KEYWORDS)


def _tokenize_name(name: str) -> List[str]:
    return [tok for tok in re.split(r"\W+", name.lower()) if tok and len(tok) > 1]


def _candidate_score(name_tokens: Sequence[str], title: str, url: str, allow_wikipedia: bool) -> Optional[int]:
    score, _, _ = _evaluate_candidate(name_tokens, title, url, allow_wikipedia)
    return score


def _evaluate_candidate(
    name_tokens: Sequence[str],
    title: str,
    url: str,
    allow_wikipedia: bool,
) -> Tuple[Optional[int], str, str]:
    normalized = _normalize_candidate_url(url)
    if not normalized.startswith(("http://", "https://")):
        return None, "invalid_scheme", normalized
    if _looks_like_blocked_source(normalized):
        return None, "blocked_domain_or_pdf", normalized

    is_wiki = _is_wikipedia_url(normalized)
    if is_wiki and not allow_wikipedia:
        return None, "wikipedia_disabled", normalized

    score = 0
    lowered_url = normalized.lower()
    lowered_title = (title or "").lower()

    if is_wiki:
        score -= 20
    else:
        score += 20

    if ".edu" in lowered_url:
        score += 12

    if any(hint in lowered_url for hint in PROFILE_URL_HINTS):
        score += 8
    if any(hint in lowered_title for hint in PROFILE_TITLE_HINTS):
        score += 8

    token_hits = 0
    for tok in name_tokens:
        if tok in lowered_title or tok in lowered_url:
            token_hits += 1
    score += min(token_hits * 4, 20)

    return score, "ok", normalized


def _candidate_sort_key(item: Mapping[str, Any], name_tokens: Sequence[str]) -> Tuple[int, int, int, int, int, int]:
    score = int(item.get("score") or 0)
    url = str(item.get("url") or "")
    title = str(item.get("title") or "")
    is_wikipedia = bool(item.get("is_wikipedia"))
    host = _hostname(url)
    personal = 1 if _is_personal_homepage_like(url, title, name_tokens) else 0
    edu = 1 if ".edu" in host else 0
    profile_hint = 1 if _url_has_profile_hint(url, title) else 0
    non_wiki = 1 if not is_wikipedia else 0
    rootish = 1 if _path_depth(url) <= 2 else 0
    return (score, personal, edu, profile_hint, non_wiki, rootish)


def _build_search_query(name: str, affiliation: str, paper_institutions: str) -> str:
    segments = [name]
    if affiliation:
        segments.append(affiliation)
    if paper_institutions:
        segments.append(paper_institutions.split(";", 1)[0])
    segments.extend(["faculty", "profile", "homepage"])
    return " ".join(seg for seg in segments if seg).strip()


def _collect_candidate_pages(
    name: str,
    affiliation: str,
    paper_institutions: str,
    fellow_settings: Mapping[str, Any],
    *,
    debug: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    from pcra.get_pdf.duckduckgo import search_duckduckgo

    max_results = int(fellow_settings["max_results"])
    query = _build_search_query(name, affiliation, paper_institutions)
    if debug is not None:
        debug["query"] = query

    search_results = search_duckduckgo(
        query,
        max_pages=2,
        max_results=max(max_results * 4, 10),
    )
    if debug is not None:
        debug["search_results_raw_count"] = len(search_results)
        debug["search_results_raw"] = [
            {"title": title, "url": _normalize_candidate_url(url or "")}
            for title, url in search_results
        ]

    candidates: List[Dict[str, Any]] = []
    name_tokens = _tokenize_name(name)
    dropped: List[Dict[str, Any]] = []

    for title, raw_url in search_results:
        if not raw_url:
            continue
        score, reason, normalized = _evaluate_candidate(
            name_tokens=name_tokens,
            title=title,
            url=raw_url,
            allow_wikipedia=bool(fellow_settings["allow_wikipedia"]),
        )
        if score is None:
            dropped.append({"title": title, "url": normalized, "reason": reason})
            continue
        candidates.append(
            {
                "title": title,
                "url": normalized,
                "score": score,
                "is_wikipedia": _is_wikipedia_url(normalized),
                "candidate_origin": "search_result",
            }
        )

    if fellow_settings.get("allow_wikipedia"):
        wiki_url = f"https://en.wikipedia.org/wiki/{name.strip().replace(' ', '_')}"
        score, _, normalized = _evaluate_candidate(
            name_tokens=name_tokens,
            title=f"{name} - Wikipedia",
            url=wiki_url,
            allow_wikipedia=True,
        )
        if score is not None:
            candidates.append(
                {
                    "title": f"{name} - Wikipedia",
                    "url": normalized,
                    "score": score,
                    "is_wikipedia": True,
                    "candidate_origin": "wikipedia_seed",
                }
            )

    candidates.sort(key=lambda item: _candidate_sort_key(item, name_tokens), reverse=True)

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in candidates:
        url = str(item.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)
        if len(deduped) >= max_results:
            break

    if debug is not None:
        debug["dropped_candidates"] = dropped
        debug["candidates_sorted"] = candidates
        debug["candidates_selected"] = deduped
    return deduped


def _fetch_static_html(url: str, timeout_s: int) -> Tuple[str, Dict[str, Any]]:
    meta: Dict[str, Any] = {
        "ok": False,
        "status_code": None,
        "content_type": None,
        "error": None,
    }
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            },
            timeout=timeout_s,
        )
        meta["status_code"] = int(response.status_code)
        meta["content_type"] = str(response.headers.get("content-type") or "")
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Static fetch failed url=%s err=%s", url, exc)
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return "", meta

    content_type = str(response.headers.get("content-type") or "").lower()
    if "application/pdf" in content_type:
        meta["error"] = "content_type_pdf"
        return "", meta
    text = response.text or ""
    meta["ok"] = True
    meta["html_chars"] = len(text)
    return text, meta


def _fallback_extract_html(html: str) -> str:
    from bs4 import BeautifulSoup  # type: ignore

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"]):
        tag.decompose()

    root = soup.find("main") or soup.find("article") or soup.body or soup
    return str(root)


def _extract_markdown_strategy_trafilatura_html(html: str, *, url: str, char_limit: int) -> str:
    if not html.strip():
        return ""

    try:
        import trafilatura  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("trafilatura package is required for fellow local extraction") from exc

    try:
        from markdownify import markdownify  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("markdownify package is required for fellow local extraction") from exc

    extracted_html = trafilatura.extract(
        html,
        url=url,
        output_format="html",
        include_comments=False,
        include_images=False,
        include_links=False,
        include_tables=False,
        include_formatting=False,
    )
    if not extracted_html:
        extracted_html = _fallback_extract_html(html)

    if not extracted_html.strip():
        return ""

    markdown = markdownify(
        extracted_html,
        heading_style="ATX",
        strip=["img", "table", "script", "style", "nav", "footer", "form", "svg", "aside"],
    )
    return _normalize_markdown(markdown, char_limit)


def _extract_markdown_strategy_trafilatura_txt(html: str, *, url: str, char_limit: int) -> str:
    if not html.strip():
        return ""
    try:
        import trafilatura  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("trafilatura package is required for fellow local extraction") from exc

    extracted_text = trafilatura.extract(
        html,
        url=url,
        output_format="txt",
        include_comments=False,
        include_images=False,
        include_links=False,
        include_tables=False,
        include_formatting=False,
    )
    if not extracted_text:
        return ""
    return _plain_text_to_markdown(extracted_text, char_limit=char_limit)


def _extract_markdown_strategy_bs4_body(html: str, *, char_limit: int) -> str:
    if not html.strip():
        return ""
    from bs4 import BeautifulSoup  # type: ignore

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"]):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    text = root.get_text("\n", strip=True) if root else ""
    return _plain_text_to_markdown(text, char_limit=char_limit)


def _extract_markdown_strategy_keyword_window(html: str, *, char_limit: int) -> str:
    if not html.strip():
        return ""
    from bs4 import BeautifulSoup  # type: ignore

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = "\n".join(seg.strip() for seg in soup.stripped_strings if seg and seg.strip())
    if not text:
        return ""
    lowered = text.lower()
    windows: List[Tuple[int, int]] = []
    for kw in EXTRACTION_HINT_KEYWORDS:
        pos = lowered.find(kw)
        if pos < 0:
            continue
        windows.append((max(0, pos - 1200), min(len(text), pos + 2600)))
    if not windows:
        return ""
    merged: List[Tuple[int, int]] = []
    for start, end in sorted(windows):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    chunks = [text[start:end] for start, end in merged]
    return _plain_text_to_markdown("\n\n".join(chunks), char_limit=char_limit)


def _extract_markdown_from_html(html: str, *, url: str, char_limit: int) -> str:
    # Backward-compatible single strategy wrapper.
    return _extract_markdown_strategy_trafilatura_html(html, url=url, char_limit=char_limit)


def _compute_extractor_quality(
    markdown: str,
    *,
    name: str,
    affiliation: str,
    paper_institutions: str,
) -> Tuple[int, Dict[str, Any]]:
    text = markdown or ""
    lowered = text.lower()
    name_tokens = _tokenize_name(name)
    name_hits = sum(tok in lowered for tok in name_tokens)
    aff = _normalize_text(affiliation)
    inst = _normalize_text((paper_institutions or "").split(";", 1)[0])
    aff_hit = bool(aff and aff in _normalize_text(text))
    inst_hit = bool(inst and inst in _normalize_text(text))

    rule_hits = {
        "acm_fellow": bool(re.search(r"\bacm\s+fellow\b", lowered)),
        "ieee_fellow": bool(re.search(r"\bieee\s+fellow\b", lowered)),
        "aaai_fellow": bool(re.search(r"\baaai\s+fellow\b", lowered)),
        "acm_ieee_fellow": bool(re.search(r"\bacm\s*/\s*ieee\s*fellow\b", lowered)),
        "biography": "biography" in lowered,
        "professor": "professor" in lowered,
    }
    fellow_hit_count = sum(
        1
        for key in ("acm_fellow", "ieee_fellow", "aaai_fellow", "acm_ieee_fellow")
        if rule_hits[key]
    )
    chars = len(text)
    score = 0
    score += min(name_hits * 4, 16)
    if aff_hit:
        score += 8
    if inst_hit:
        score += 6
    score += min(fellow_hit_count * 20, 40)
    if rule_hits["biography"]:
        score += 6
    if rule_hits["professor"]:
        score += 4
    if 400 <= chars <= 12000:
        score += 10
    elif chars > 12000:
        score += 6
    elif chars >= 180:
        score += 4

    noise_terms = ("home", "menu", "about", "news", "contact", "copyright")
    noise_hits = sum(lowered.count(term) for term in noise_terms)
    if chars > 0:
        noise_ratio = noise_hits / max(1, chars // 50)
    else:
        noise_ratio = 0.0
    if noise_ratio > 0.4:
        score -= 6

    detail = {
        "name_hits": name_hits,
        "affiliation_hit": aff_hit,
        "institution_hit": inst_hit,
        "fellow_hit_count": fellow_hit_count,
        "rule_hits": rule_hits,
        "chars": chars,
        "noise_ratio": round(noise_ratio, 3),
    }
    return score, detail


def _extract_markdown_attempts(
    html: str,
    *,
    url: str,
    name: str,
    affiliation: str,
    paper_institutions: str,
    char_limit: int,
    mode: str,
) -> List[Dict[str, Any]]:
    strategies: List[Tuple[str, Any]] = [
        ("trafilatura_html", lambda: _extract_markdown_strategy_trafilatura_html(html, url=url, char_limit=char_limit)),
        ("trafilatura_txt", lambda: _extract_markdown_strategy_trafilatura_txt(html, url=url, char_limit=char_limit)),
        ("bs4_body", lambda: _extract_markdown_strategy_bs4_body(html, char_limit=char_limit)),
        ("keyword_window", lambda: _extract_markdown_strategy_keyword_window(html, char_limit=char_limit)),
    ]
    if mode in EXTRACT_MODES and mode != "auto":
        strategies = [x for x in strategies if x[0] == mode]
    attempts: List[Dict[str, Any]] = []
    for strategy_name, run in strategies:
        attempt: Dict[str, Any] = {"strategy": strategy_name, "error": None}
        try:
            markdown = run() or ""
            markdown = _normalize_markdown(markdown, char_limit=char_limit)
        except Exception as exc:  # noqa: BLE001
            markdown = ""
            attempt["error"] = f"{type(exc).__name__}: {exc}"
        quality_score, detail = _compute_extractor_quality(
            markdown,
            name=name,
            affiliation=affiliation,
            paper_institutions=paper_institutions,
        )
        attempt["quality_score"] = quality_score
        attempt["quality_detail"] = detail
        attempt["markdown"] = markdown
        attempt["markdown_chars"] = len(markdown)
        attempts.append(attempt)
    return attempts


def _select_best_markdown_attempt(attempts: Sequence[Mapping[str, Any]]) -> Tuple[str, str, str]:
    if not attempts:
        return "", "", "no_attempts"
    ranked = sorted(
        attempts,
        key=lambda a: (
            int(a.get("quality_score") or 0),
            int(a.get("markdown_chars") or 0),
        ),
        reverse=True,
    )
    best = ranked[0]
    markdown = str(best.get("markdown") or "")
    strategy = str(best.get("strategy") or "")
    reason = f"highest_quality_score={int(best.get('quality_score') or 0)}"
    return markdown, strategy, reason


def _extract_derived_homepage_candidates(
    markdown: str,
    *,
    current_url: str,
    allow_wikipedia: bool,
    name_tokens: Sequence[str],
) -> List[str]:
    urls = _extract_urls(markdown)
    candidates: List[str] = []
    current_host = _hostname(current_url)
    for raw in urls:
        norm = _normalize_candidate_url(raw)
        if not norm.startswith(("http://", "https://")):
            continue
        if _looks_like_blocked_source(norm):
            continue
        if _is_wikipedia_url(norm) and not allow_wikipedia:
            continue
        host = _hostname(norm)
        if not host:
            continue
        # Bias toward same academic domain or personal-homepage like URLs.
        related_domain = current_host and (
            host.endswith(current_host) or current_host.endswith(host) or ".edu" in host
        )
        personal_like = _is_personal_homepage_like(norm, "", name_tokens) or ("/~" in norm)
        name_hint = any(tok in norm.lower() for tok in name_tokens)
        if related_domain or personal_like or name_hint:
            candidates.append(norm)
    return _dedupe_urls(candidates)


def _detect_rule_based_honors(markdown: str) -> Dict[str, Any]:
    statuses = {org: "Unknown" for org in HONOR_ORGS}
    matches: List[Dict[str, Any]] = []
    if not markdown:
        return {"statuses_org": statuses, "matches": matches}

    compact = re.sub(r"\s+", " ", markdown)
    for pattern, orgs, source in RULE_POSITIVE_PATTERNS:
        for m in pattern.finditer(compact):
            start, end = m.span()
            snippet = compact[max(0, start - 80) : min(len(compact), end + 120)]
            for org in orgs:
                statuses[org] = "Yes"
            matches.append(
                {
                    "type": "positive",
                    "source": source,
                    "pattern": pattern.pattern,
                    "matched_text": m.group(0),
                    "orgs": list(orgs),
                    "snippet": snippet,
                }
            )

    for pattern, org in RULE_NEGATIVE_PATTERNS:
        for m in pattern.finditer(compact):
            if statuses.get(org) == "Yes":
                continue
            statuses[org] = "No"
            start, end = m.span()
            snippet = compact[max(0, start - 80) : min(len(compact), end + 120)]
            matches.append(
                {
                    "type": "negative",
                    "pattern": pattern.pattern,
                    "matched_text": m.group(0),
                    "orgs": [org],
                    "snippet": snippet,
                }
            )

    return {"statuses_org": statuses, "matches": matches}


def _fetch_dynamic_html(url: str, *, driver: Any, wait_timeout_s: int) -> Tuple[str, Dict[str, Any]]:
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    meta: Dict[str, Any] = {"ok": False, "timed_out": False, "error": None}
    try:
        driver.get(url)
        try:
            WebDriverWait(driver, wait_timeout_s).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            logger.debug("Dynamic fetch timeout url=%s", url)
            meta["timed_out"] = True
        html = driver.page_source or ""
        meta["ok"] = bool(html)
        meta["html_chars"] = len(html)
        return html, meta
    except Exception as exc:  # noqa: BLE001
        logger.debug("Dynamic fetch failed url=%s err=%s", url, exc)
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return "", meta


def _call_openai_chat_json(
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout_s: int,
    max_tokens: int,
    messages: List[Dict[str, str]],
) -> str:
    try:
        from openai import OpenAI  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("openai package is required for local fellow LLM calls") from exc

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s)
    params: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    try:
        completion = client.chat.completions.create(**params)
    except Exception:
        params.pop("response_format", None)
        completion = client.chat.completions.create(**params)

    message = completion.choices[0].message
    return message.content or ""


def _parse_local_llm_result(text: str) -> Dict[str, Any]:
    data = _parse_json_from_text(text)

    is_target = _coerce_bool(data.get("is_target_scholar"), default=False)
    has_valid_profile = _coerce_bool(data.get("has_valid_profile_content"), default=False)
    fellow_obj = data.get("fellow")
    if not isinstance(fellow_obj, dict):
        fellow_obj = {}

    statuses_org = {org: "Unknown" for org in HONOR_ORGS}
    years = {org: "N/A" for org in HONOR_ORGS}

    for org in HONOR_ORGS:
        entry = fellow_obj.get(org)
        if entry is None:
            key = ORG_TO_KEY[org]
            entry = fellow_obj.get(key)

        status_value: Any = None
        year_value: Any = None
        if isinstance(entry, dict):
            status_value = entry.get("status")
            year_value = entry.get("year")
        elif isinstance(entry, str):
            status_value = entry

        statuses_org[org] = _normalize_status(status_value)
        if year_value is not None:
            years[org] = str(year_value).strip() or "N/A"

    if not is_target or not has_valid_profile:
        statuses_org = {org: "Unknown" for org in HONOR_ORGS}

    return {
        "is_target_scholar": is_target,
        "has_valid_profile_content": has_valid_profile,
        "statuses_org": statuses_org,
        "years": years,
    }


def _call_local_text_llm_for_honor_check(
    *,
    name: str,
    affiliation: str,
    paper_institutions: str,
    source_url: str,
    markdown: str,
    text_settings: Mapping[str, Any],
) -> Tuple[Dict[str, Any], str]:
    user_payload = (
        f"Scholar name: {name or 'Unknown'}\n"
        f"Affiliation: {affiliation or 'Unknown'}\n"
        f"Paper institutions: {paper_institutions or 'Unknown'}\n"
        f"Source URL: {source_url}\n"
        f"Page markdown excerpt:\n{markdown}\n"
    )
    messages = [
        {"role": "system", "content": PROMPT_LOCAL_PAGE_HONOR_CHECK},
        {"role": "user", "content": user_payload},
    ]

    max_retries = int(text_settings.get("max_retries") or 2)
    last_error: Optional[Exception] = None
    for _ in range(max_retries + 1):
        try:
            raw = _call_openai_chat_json(
                base_url=str(text_settings["api_base"]),
                api_key=str(text_settings["api_key"]),
                model=str(text_settings["model"]),
                timeout_s=int(text_settings["timeout_s"]),
                max_tokens=int(text_settings["max_tokens"]),
                messages=messages,
            )
            parsed = _parse_local_llm_result(raw)
            return parsed, raw
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"local_llm_call_failed: {last_error}")


def _merge_candidate_statuses(
    merged_org: Dict[str, str],
    candidate_org: Mapping[str, str],
    *,
    source_url: str,
    source_by_org: Dict[str, str],
) -> None:
    for org in HONOR_ORGS:
        current = merged_org.get(org) or "Unknown"
        incoming = _normalize_status(candidate_org.get(org))
        if current == "Yes":
            continue
        if incoming == "Yes":
            merged_org[org] = "Yes"
            source_by_org[org] = source_url
        elif incoming == "No" and current == "Unknown":
            merged_org[org] = "No"
            source_by_org.setdefault(org, source_url)


def _merge_llm_and_rule_statuses(
    llm_statuses_org: Mapping[str, Any],
    *,
    rule_statuses_org: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    merged = {org: _normalize_status(llm_statuses_org.get(org)) for org in HONOR_ORGS}
    if not rule_statuses_org:
        return merged
    for org in HONOR_ORGS:
        rule_status = _normalize_status(rule_statuses_org.get(org))
        if rule_status == "Yes":
            merged[org] = "Yes"
        elif rule_status == "No" and merged[org] == "Unknown":
            merged[org] = "No"
    return merged


def _lookup_via_local_web_and_llm(
    name: str,
    affiliation: str,
    paper_institutions: str,
    fellow_settings: Mapping[str, Any],
    text_settings: Mapping[str, Any],
    *,
    debug: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, str], List[str], str, Optional[str]]:
    local_debug: Dict[str, Any] = {}
    if debug is not None:
        debug["settings"] = {
            "fellow": _settings_for_debug(fellow_settings),
            "text": _settings_for_debug(text_settings),
        }
        debug["search"] = local_debug

    try:
        candidates = _collect_candidate_pages(
            name,
            affiliation,
            paper_institutions,
            fellow_settings,
            debug=local_debug,
        )
    except Exception as exc:  # noqa: BLE001
        if debug is not None:
            debug["error"] = f"{type(exc).__name__}: {exc}"
        return _default_statuses(), [], "", f"{type(exc).__name__}: {exc}"

    if not candidates:
        if debug is not None:
            debug["candidates_processed"] = []
        return _default_statuses(), [], "", None

    max_candidates = int(fellow_settings["max_results"])
    name_tokens = _tokenize_name(name)
    queue: List[Dict[str, Any]] = list(candidates[:max_candidates])
    seen_candidate_urls = {str(item.get("url") or "") for item in queue}
    if debug is not None:
        local_debug["candidate_queue_initial"] = queue

    merged_org_statuses = {org: "Unknown" for org in HONOR_ORGS}
    source_by_org: Dict[str, str] = {}
    raw_outputs: List[str] = []
    technical_errors: List[str] = []
    global_rule_matches: List[Dict[str, Any]] = []
    candidate_debugs: List[Dict[str, Any]] = []
    debug_markdown_limit = int(fellow_settings.get("debug_markdown_max_chars") or 20000)

    driver = None
    try:
        idx = 0
        processed = 0
        while idx < len(queue) and processed < max_candidates:
            candidate = queue[idx]
            idx += 1
            processed += 1
            url = str(candidate.get("url") or "")
            if not url:
                continue
            candidate_debug: Dict[str, Any] = {
                "candidate_index": processed,
                "title": candidate.get("title"),
                "url": url,
                "score": candidate.get("score"),
                "candidate_origin": candidate.get("candidate_origin"),
            }
            candidate_debugs.append(candidate_debug)

            static_html, static_meta = _fetch_static_html(url, timeout_s=int(fellow_settings["timeout_s"]))
            candidate_debug["phase1_static_fetch"] = static_meta
            static_markdown = ""
            static_attempts: List[Dict[str, Any]] = []
            if static_html:
                try:
                    static_attempts = _extract_markdown_attempts(
                        static_html,
                        url=url,
                        name=name,
                        affiliation=affiliation,
                        paper_institutions=paper_institutions,
                        char_limit=int(fellow_settings["profile_char_limit"]),
                        mode=str(fellow_settings.get("extract_markdown_mode") or "auto"),
                    )
                    static_markdown, selected_strategy, selected_reason = _select_best_markdown_attempt(
                        static_attempts
                    )
                    candidate_debug["phase1_selected_extractor"] = selected_strategy
                    candidate_debug["phase1_selected_reason"] = selected_reason
                    candidate_debug.setdefault("selected_extractor", selected_strategy)
                    candidate_debug.setdefault("selected_reason", selected_reason)
                except Exception as exc:  # noqa: BLE001
                    err = f"static_extract_failed:{type(exc).__name__}:{exc}"
                    technical_errors.append(err)
                    candidate_debug["phase1_extract_error"] = err
            if static_attempts:
                candidate_debug["phase1_extractor_attempts"] = [
                    {
                        "strategy": a.get("strategy"),
                        "quality_score": a.get("quality_score"),
                        "keyword_hits": ((a.get("quality_detail") or {}).get("rule_hits") or {}),
                        "markdown_chars": a.get("markdown_chars"),
                        "error": a.get("error"),
                        "markdown": _truncate_text(
                            str(a.get("markdown") or ""),
                            limit=debug_markdown_limit,
                        ),
                    }
                    for a in static_attempts
                ]
            candidate_debug["phase1_markdown_chars"] = len(static_markdown)
            candidate_debug["phase1_markdown_preview"] = _truncate_text(
                static_markdown,
                limit=debug_markdown_limit,
            )

            phase1_valid = False
            if static_markdown and len(static_markdown) >= int(fellow_settings["min_profile_chars"]):
                try:
                    parsed, raw = _call_local_text_llm_for_honor_check(
                        name=name,
                        affiliation=affiliation,
                        paper_institutions=paper_institutions,
                        source_url=url,
                        markdown=static_markdown,
                        text_settings=text_settings,
                    )
                    candidate_debug["phase1_llm_parsed"] = parsed
                    candidate_debug["phase1_llm_raw"] = _truncate_text(raw, limit=1200)
                    raw_outputs.append(raw)
                    if parsed.get("is_target_scholar") and parsed.get("has_valid_profile_content"):
                        phase1_valid = True
                        rule_result = {"statuses_org": {org: "Unknown" for org in HONOR_ORGS}, "matches": []}
                        if bool(fellow_settings.get("rule_assisted_honor_detection")):
                            rule_result = _detect_rule_based_honors(static_markdown)
                            candidate_debug["phase1_rule_matches"] = rule_result.get("matches") or []
                            for m in rule_result.get("matches") or []:
                                global_rule_matches.append(
                                    {
                                        "url": url,
                                        "phase": "phase1",
                                        "match": m,
                                    }
                                )
                        merged_candidate = _merge_llm_and_rule_statuses(
                            parsed.get("statuses_org") or {},
                            rule_statuses_org=rule_result.get("statuses_org"),
                        )
                        candidate_debug["phase1_final_merge_decision"] = {
                            "llm_statuses_org": parsed.get("statuses_org") or {},
                            "rule_statuses_org": rule_result.get("statuses_org") or {},
                            "merged_statuses_org": merged_candidate,
                        }
                        _merge_candidate_statuses(
                            merged_org_statuses,
                            merged_candidate,
                            source_url=url,
                            source_by_org=source_by_org,
                        )
                except Exception as exc:  # noqa: BLE001
                    err = f"phase1_llm_failed:{type(exc).__name__}:{exc}"
                    technical_errors.append(err)
                    candidate_debug["phase1_llm_error"] = err
            else:
                candidate_debug["phase1_skipped_reason"] = (
                    "markdown_too_short_or_empty"
                    if static_html
                    else "static_html_unavailable"
                )

            derived_inserted: List[Dict[str, Any]] = []
            if static_markdown:
                derived_urls = _extract_derived_homepage_candidates(
                    static_markdown,
                    current_url=url,
                    allow_wikipedia=bool(fellow_settings.get("allow_wikipedia")),
                    name_tokens=name_tokens,
                )
                for derived_url in derived_urls:
                    if derived_url in seen_candidate_urls:
                        continue
                    score = int(candidate.get("score") or 0) + 50
                    derived_item = {
                        "title": f"Derived homepage from {url}",
                        "url": derived_url,
                        "score": score,
                        "is_wikipedia": _is_wikipedia_url(derived_url),
                        "candidate_origin": "derived_homepage_url",
                    }
                    queue.insert(idx, derived_item)
                    seen_candidate_urls.add(derived_url)
                    dropped_item = None
                    if len(queue) > max_candidates:
                        dropped_item = queue.pop()
                        if str(dropped_item.get("url") or "") == derived_url:
                            seen_candidate_urls.discard(derived_url)
                    if dropped_item and str(dropped_item.get("url") or "") != derived_url:
                        derived_inserted.append(
                            {
                                "added_url": derived_url,
                                "added_score": score,
                                "dropped_url": dropped_item.get("url"),
                            }
                        )
                    elif not dropped_item:
                        derived_inserted.append(
                            {
                                "added_url": derived_url,
                                "added_score": score,
                                "dropped_url": None,
                            }
                        )
            if derived_inserted:
                candidate_debug["derived_candidates_added"] = derived_inserted

            if phase1_valid:
                candidate_debug["phase1_accepted"] = True
                continue

            # If static fetch failed entirely, treat as no-evidence rather than
            # forcing dynamic rendering (which can surface environment-only errors).
            if not static_html:
                candidate_debug["phase2_skipped_reason"] = "static_fetch_failed"
                continue

            if driver is None:
                try:
                    from pcra.get_pdf.selenium_driver import create_chrome_driver

                    driver = create_chrome_driver(headless=True)
                except Exception as exc:  # noqa: BLE001
                    err = f"selenium_init_failed:{type(exc).__name__}:{exc}"
                    technical_errors.append(err)
                    candidate_debug["phase2_selenium_init_error"] = err
                    continue

            dynamic_html, dynamic_meta = _fetch_dynamic_html(
                url,
                driver=driver,
                wait_timeout_s=int(fellow_settings["dynamic_wait_s"]),
            )
            candidate_debug["phase2_dynamic_fetch"] = dynamic_meta
            if not dynamic_html:
                candidate_debug["phase2_skipped_reason"] = "dynamic_html_unavailable"
                continue

            dynamic_markdown = ""
            dynamic_attempts: List[Dict[str, Any]] = []
            try:
                dynamic_attempts = _extract_markdown_attempts(
                    dynamic_html,
                    url=url,
                    name=name,
                    affiliation=affiliation,
                    paper_institutions=paper_institutions,
                    char_limit=int(fellow_settings["profile_char_limit"]),
                    mode=str(fellow_settings.get("extract_markdown_mode") or "auto"),
                )
                dynamic_markdown, selected_strategy, selected_reason = _select_best_markdown_attempt(
                    dynamic_attempts
                )
                candidate_debug["phase2_selected_extractor"] = selected_strategy
                candidate_debug["phase2_selected_reason"] = selected_reason
                candidate_debug.setdefault("selected_extractor", selected_strategy)
                candidate_debug.setdefault("selected_reason", selected_reason)
            except Exception as exc:  # noqa: BLE001
                err = f"dynamic_extract_failed:{type(exc).__name__}:{exc}"
                technical_errors.append(err)
                candidate_debug["phase2_extract_error"] = err
            if dynamic_attempts:
                candidate_debug["phase2_extractor_attempts"] = [
                    {
                        "strategy": a.get("strategy"),
                        "quality_score": a.get("quality_score"),
                        "keyword_hits": ((a.get("quality_detail") or {}).get("rule_hits") or {}),
                        "markdown_chars": a.get("markdown_chars"),
                        "error": a.get("error"),
                        "markdown": _truncate_text(
                            str(a.get("markdown") or ""),
                            limit=debug_markdown_limit,
                        ),
                    }
                    for a in dynamic_attempts
                ]
            candidate_debug["phase2_markdown_chars"] = len(dynamic_markdown)
            candidate_debug["phase2_markdown_preview"] = _truncate_text(
                dynamic_markdown,
                limit=debug_markdown_limit,
            )

            if not dynamic_markdown or len(dynamic_markdown) < int(fellow_settings["min_profile_chars"]):
                candidate_debug["phase2_skipped_reason"] = "dynamic_markdown_too_short_or_empty"
                continue

            try:
                parsed, raw = _call_local_text_llm_for_honor_check(
                    name=name,
                    affiliation=affiliation,
                    paper_institutions=paper_institutions,
                    source_url=url,
                    markdown=dynamic_markdown,
                    text_settings=text_settings,
                )
                candidate_debug["phase2_llm_parsed"] = parsed
                candidate_debug["phase2_llm_raw"] = _truncate_text(raw, limit=1200)
                raw_outputs.append(raw)
                if parsed.get("is_target_scholar") and parsed.get("has_valid_profile_content"):
                    rule_result = {"statuses_org": {org: "Unknown" for org in HONOR_ORGS}, "matches": []}
                    if bool(fellow_settings.get("rule_assisted_honor_detection")):
                        rule_result = _detect_rule_based_honors(dynamic_markdown)
                        candidate_debug["phase2_rule_matches"] = rule_result.get("matches") or []
                        for m in rule_result.get("matches") or []:
                            global_rule_matches.append(
                                {
                                    "url": url,
                                    "phase": "phase2",
                                    "match": m,
                                }
                            )
                    merged_candidate = _merge_llm_and_rule_statuses(
                        parsed.get("statuses_org") or {},
                        rule_statuses_org=rule_result.get("statuses_org"),
                    )
                    candidate_debug["phase2_final_merge_decision"] = {
                        "llm_statuses_org": parsed.get("statuses_org") or {},
                        "rule_statuses_org": rule_result.get("statuses_org") or {},
                        "merged_statuses_org": merged_candidate,
                    }
                    _merge_candidate_statuses(
                        merged_org_statuses,
                        merged_candidate,
                        source_url=url,
                        source_by_org=source_by_org,
                    )
                    candidate_debug["phase2_accepted"] = True
            except Exception as exc:  # noqa: BLE001
                err = f"phase2_llm_failed:{type(exc).__name__}:{exc}"
                technical_errors.append(err)
                candidate_debug["phase2_llm_error"] = err
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:  # noqa: BLE001
                pass

    statuses = _statuses_from_org_map(merged_org_statuses)
    sources = _dedupe_urls([source_by_org[org] for org in HONOR_ORGS if org in source_by_org])
    raw_text = "\n\n".join(raw_outputs)
    if debug is not None:
        debug["candidates_processed"] = candidate_debugs
        debug["candidate_queue_final"] = queue
        debug["technical_errors"] = technical_errors
        debug["rule_matches"] = global_rule_matches
        debug["merged_org_statuses"] = merged_org_statuses
        debug["statuses"] = statuses
        debug["sources"] = sources
        debug["final_merge_decision"] = {
            "source_by_org": source_by_org,
            "merged_org_statuses": merged_org_statuses,
        }

    if technical_errors and _all_unknown(statuses):
        return statuses, sources, raw_text, technical_errors[0]
    return statuses, sources, raw_text, None


def lookup_fellow_status(
    name: str,
    affiliation: Optional[str],
    *,
    institutions: Optional[List[Dict[str, Any]]] = None,
    llm_config_path: Optional[Path],
    max_results: Optional[int],
    timeout_s: Optional[int] = None,
    max_retries: Optional[int] = None,
    cache_path: Optional[Path] = None,
    debug_dir: Optional[Path] = None,
) -> Tuple[Dict[str, str], List[str], Optional[str]]:
    """Return (fellow_status, sources, error)."""
    debug: Optional[Dict[str, Any]] = None
    resolved_debug_dir: Optional[Path] = None
    if debug_dir is not None:
        resolved_debug_dir = Path(debug_dir)
        debug = {
            "started_at": _utc_now_iso(),
            "input": {
                "name": name,
                "affiliation": affiliation,
                "institutions": institutions or [],
                "llm_config_path": str(llm_config_path) if llm_config_path else None,
                "max_results": max_results,
                "timeout_s": timeout_s,
                "max_retries": max_retries,
                "cache_path": str(cache_path) if cache_path else None,
            },
        }

    if not name:
        if debug is not None:
            debug["error_stage"] = "validate_input"
        return _finalize_lookup_result(
            statuses=_default_statuses(),
            sources=[],
            error="missing_name",
            debug=debug,
            debug_dir=resolved_debug_dir,
        )

    if not llm_config_path or not llm_config_path.exists():
        if debug is not None:
            debug["error_stage"] = "validate_config"
        return _finalize_lookup_result(
            statuses=_default_statuses(),
            sources=[],
            error="missing_llm_config",
            debug=debug,
            debug_dir=resolved_debug_dir,
        )

    try:
        config = _load_yaml(llm_config_path)
        fellow_settings = _read_fellow_lookup_settings(config, max_results, timeout_s, max_retries)
    except Exception as exc:  # noqa: BLE001
        if debug is not None:
            debug["error_stage"] = "load_config"
        return _finalize_lookup_result(
            statuses=_default_statuses(),
            sources=[],
            error=f"{type(exc).__name__}: {exc}",
            debug=debug,
            debug_dir=resolved_debug_dir,
        )

    mode = str(fellow_settings["mode"])
    paper_institutions = _format_institutions(institutions)
    if debug is not None:
        debug["mode"] = mode
        debug["fellow_settings"] = _settings_for_debug(fellow_settings)
        debug["paper_institutions"] = paper_institutions

    cache_meta: Dict[str, Any] = {
        "mode": mode,
        "max_results": fellow_settings.get("max_results"),
        "allow_wikipedia": fellow_settings.get("allow_wikipedia"),
        "profile_char_limit": fellow_settings.get("profile_char_limit"),
        "extract_markdown_mode": fellow_settings.get("extract_markdown_mode"),
        "rule_assisted_honor_detection": fellow_settings.get("rule_assisted_honor_detection"),
        "local_model": "",
        "openrouter_model": "",
    }
    text_settings: Optional[Dict[str, Any]] = None
    if mode in {"local_only", "local_with_fallback"}:
        try:
            text_settings = _read_text_llm_settings(config, timeout_s, max_retries)
            cache_meta["local_model"] = text_settings.get("model")
            if debug is not None:
                debug["text_settings"] = _settings_for_debug(text_settings)
        except Exception as exc:  # noqa: BLE001
            if debug is not None:
                debug["error_stage"] = "load_text_settings"
            return _finalize_lookup_result(
                statuses=_default_statuses(),
                sources=[],
                error=f"{type(exc).__name__}: {exc}",
                debug=debug,
                debug_dir=resolved_debug_dir,
            )

    if isinstance(config.get("openrouter_web_search"), dict):
        cache_meta["openrouter_model"] = str((config.get("openrouter_web_search") or {}).get("model") or "")

    cache_key = None
    cache = None
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache = _load_cache(cache_path)
        cache_key = _make_cache_key(name, affiliation or "", paper_institutions, cache_meta)
        if debug is not None:
            debug["cache"] = {"enabled": True, "key": cache_key}
        cached = _get_cached(cache, cache_key)
        if cached:
            statuses = _normalize_cached_statuses(cached.get("statuses"))
            sources = _dedupe_urls(cached.get("sources") or [])
            if debug is not None:
                debug["cache"]["hit"] = True
                debug["cache"]["cached_statuses"] = statuses
                debug["cache"]["cached_sources"] = sources
            return _finalize_lookup_result(
                statuses=statuses,
                sources=sources,
                error=None,
                debug=debug,
                debug_dir=resolved_debug_dir,
            )
        if debug is not None:
            debug["cache"]["hit"] = False
    elif debug is not None:
        debug["cache"] = {"enabled": False}

    statuses = _default_statuses()
    sources: List[str] = []
    raw_text = ""
    error: Optional[str] = None

    if mode == "openrouter_only":
        try:
            openrouter_settings = _read_openrouter_settings(config, max_results, timeout_s, max_retries)
        except Exception as exc:  # noqa: BLE001
            if debug is not None:
                debug["error_stage"] = "load_openrouter_settings"
            return _finalize_lookup_result(
                statuses=_default_statuses(),
                sources=[],
                error=f"{type(exc).__name__}: {exc}",
                debug=debug,
                debug_dir=resolved_debug_dir,
            )

        openrouter_debug: Dict[str, Any] = {}
        if debug is not None:
            debug["openrouter"] = openrouter_debug
        statuses, sources, raw_text, error = _lookup_via_openrouter(
            name,
            affiliation or "",
            paper_institutions,
            openrouter_settings,
            debug=openrouter_debug,
        )
    else:
        assert text_settings is not None
        local_debug: Dict[str, Any] = {}
        if debug is not None:
            debug["local"] = local_debug
        statuses, sources, raw_text, error = _lookup_via_local_web_and_llm(
            name,
            affiliation or "",
            paper_institutions,
            fellow_settings,
            text_settings,
            debug=local_debug,
        )

        should_fallback = mode == "local_with_fallback" and (error is not None or _all_unknown(statuses))
        if debug is not None:
            debug["should_fallback"] = should_fallback
        if should_fallback:
            fallback_debug: Dict[str, Any] = {}
            if debug is not None:
                debug["fallback_openrouter"] = fallback_debug
            try:
                openrouter_settings = _read_openrouter_settings(config, max_results, timeout_s, max_retries)
                fb_statuses, fb_sources, fb_raw, fb_error = _lookup_via_openrouter(
                    name,
                    affiliation or "",
                    paper_institutions,
                    openrouter_settings,
                    debug=fallback_debug,
                )
            except Exception as exc:  # noqa: BLE001
                fb_error = f"{type(exc).__name__}: {exc}"
                fb_statuses, fb_sources, fb_raw = _default_statuses(), [], ""
                fallback_debug["error"] = fb_error

            if fb_error is None:
                statuses = fb_statuses
                sources = fb_sources
                raw_text = fb_raw or raw_text
                error = None
            else:
                error = f"fallback_failed:{fb_error}"
                if raw_text and fb_raw:
                    raw_text = f"{raw_text}\n\n{fb_raw}"

    if cache is not None and cache_key is not None and error is None:
        _store_cache(cache, cache_key, statuses, _dedupe_urls(sources), raw_text)
        _save_cache(cache_path, cache)
        if debug is not None:
            debug.setdefault("cache", {})
            debug["cache"]["stored"] = True

    if debug is not None:
        debug["raw_text_preview"] = _truncate_text(raw_text, limit=2000)

    return _finalize_lookup_result(
        statuses=statuses,
        sources=sources,
        error=error,
        debug=debug,
        debug_dir=resolved_debug_dir,
    )
