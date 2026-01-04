"""Fellow lookup via OpenRouter web search."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


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
- Source of information (official website, announcement, or homepage)

Do NOT infer or guess.
If no reliable evidence is found, mark the status as Unknown.
Return results in a structured, per-organization format.

STRICT CONSTRAINTS:

1. Prefer official HTML pages.
2. Evidence limit: use at most ONE reliable source per organization.
3. Search budget: shallow search only; if evidence is not found quickly, return "Unknown".
4. Output format (must follow exactly):

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

HONOR_ORGS = ("IEEE Fellow", "ACM Fellow", "AAAI Fellow")
PLACEHOLDER_API_KEYS = {"", "YOUR_OPENROUTER_API_KEY", "OPENROUTER_API_KEY", "REPLACE_ME"}
CACHE_TTL_DAYS = 180
CACHE_VERSION = 1


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


def _http_post_json(
    url: str, headers: Mapping[str, str], payload: Mapping[str, Any], timeout_s: int, max_retries: int
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
        except Exception as exc:
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


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.strip().lower())


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
        segments = [seg for seg in [name, f"ror={ror}" if ror else None, f"country={country}" if country else None] if seg]
        if segments:
            parts.append(" | ".join(segments))
    return "; ".join(parts)


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


def _make_cache_key(
    name: str,
    affiliation: str,
    paper_institutions: str,
    settings: Mapping[str, Any],
) -> str:
    parts = [
        _normalize_text(name),
        _normalize_text(affiliation),
        _normalize_text(paper_institutions),
        str(settings.get("model")),
        int(settings.get("max_results") or 0),
    ]
    return json.dumps(parts, ensure_ascii=True, separators=(",", ":"))


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
        "statuses": dict(statuses),
        "sources": list(sources),
        "raw_text": raw_text,
    }


def _default_statuses() -> Dict[str, str]:
    return {"ieee": "Unknown", "acm": "Unknown", "aaai": "Unknown"}


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
) -> Tuple[Dict[str, str], List[str], Optional[str]]:
    """Return (fellow_status, sources, error)."""

    if not name:
        return _default_statuses(), [], "missing_name"

    if not llm_config_path or not llm_config_path.exists():
        return _default_statuses(), [], "missing_llm_config"

    try:
        config = _load_yaml(llm_config_path)
        settings = _read_openrouter_settings(config, max_results, timeout_s, max_retries)
    except Exception as exc:
        return _default_statuses(), [], f"{type(exc).__name__}: {exc}"

    paper_institutions = _format_institutions(institutions)
    cache_key = None
    cache = None
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache = _load_cache(cache_path)
        cache_key = _make_cache_key(name, affiliation or "", paper_institutions, settings)
        cached = _get_cached(cache, cache_key)
        if cached:
            statuses = cached.get("statuses") or {}
            sources = cached.get("sources") or []
            return {
                "ieee": str(statuses.get("IEEE Fellow") or "Unknown"),
                "acm": str(statuses.get("ACM Fellow") or "Unknown"),
                "aaai": str(statuses.get("AAAI Fellow") or "Unknown"),
            }, list(sources), None

    prompt = PROMPT_HONOR_CHECK.format(
        name=name,
        affiliation=affiliation or "Unknown",
        paper_institutions=paper_institutions or "Unknown",
    )
    try:
        content, annotations = _call_openrouter_chat(prompt, settings)
    except Exception as exc:
        return _default_statuses(), [], f"{type(exc).__name__}: {exc}"

    raw_statuses = _parse_honor_statuses(content)
    statuses = {
        "ieee": raw_statuses.get("IEEE Fellow") or "Unknown",
        "acm": raw_statuses.get("ACM Fellow") or "Unknown",
        "aaai": raw_statuses.get("AAAI Fellow") or "Unknown",
    }

    sources = _collect_citations(annotations)
    if not sources:
        sources = _collect_urls_from_text(content)
    deduped: List[str] = []
    seen = set()
    for url in sources:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)

    if cache is not None and cache_key is not None:
        _store_cache(cache, cache_key, raw_statuses, deduped, content)
        _save_cache(cache_path, cache)

    return statuses, deduped, None
