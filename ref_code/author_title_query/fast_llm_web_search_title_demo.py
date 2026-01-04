#!/usr/bin/env python3
"""
OpenRouter web-search demo for scholar honor/title lookup (fast path).

Example:
  python ref_code/author_title_query/fast_llm_web_search_title_demo.py \
    --name "Guoliang Li" --affiliation "Tsinghua University"

  python ref_code/author_title_query/fast_llm_web_search_title_demo.py \
    --name "Qiang Yang" --affiliation "Hong Kong University of Science and Technology"

  # Or: use two or more spaces to separate name and affiliation
  python ref_code/author_title_query/fast_llm_web_search_title_demo.py \\
    --query "Qiang Yang  Hong Kong University of Science and Technology"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


PROMPT_HONOR_CHECK = """You are performing a precise honor verification task for a scholar.

Given the following information:
- Scholar name: {name}
- Affiliation: {affiliation}

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
   - Do NOT open or cite PDF files in any situation.

2. Evidence limit:
   - Use at most ONE reliable source per organization.
   - Stop searching once evidence is found.

3. Search budget:
   - Shallow search only.
   - If evidence is not found quickly, return "Unknown".
   - Do NOT attempt exhaustive verification for No / Unknown.

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

PROMPT_FALLBACK_DISCOVERY = """You are performing a fallback discovery task for a scholar's academic profile.

Given the following information:
- Scholar name: {name}
- Affiliation: {affiliation}

Please list other major academic positions or honors held by this scholar,
excluding IEEE Fellow, ACM Fellow, and AAAI Fellow.

Focus only on:
- Academic positions (e.g., Professor, Chair, Director)
- Major national or international honors
- Other professional society fellowships or equivalent distinctions

For each item, provide:
- Title or honor name
- Awarding organization or institution
- Year (if available)
- Source of information

Do NOT attempt to be exhaustive.
Only include items supported by reliable public sources.
"""

HONOR_ORGS = ("IEEE Fellow", "ACM Fellow", "AAAI Fellow")
PLACEHOLDER_API_KEYS = {
    "",
    "YOUR_OPENROUTER_API_KEY",
    "OPENROUTER_API_KEY",
    "REPLACE_ME",
}
CACHE_TTL_DAYS = 180
CACHE_FILENAME = "fast_llm_web_search_title_cache.json"
CACHE_VERSION = 1


def _load_minimal_yaml(path: Path) -> Dict[str, Any]:
    """Tiny YAML loader for simple 'section: {k: v}' configs (no lists)."""
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


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.strip().lower())


def _resolve_model(settings: Mapping[str, Any]) -> str:
    model = str(settings["model"])
    if settings["web_search_mode"] == "online" and not model.endswith(":online"):
        model = f"{model}:online"
    return model


def _cache_path() -> Path:
    return Path(__file__).with_name(CACHE_FILENAME)


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


def _make_cache_key(name: str, affiliation: str, settings: Mapping[str, Any]) -> str:
    parts = [
        _normalize_text(name),
        _normalize_text(affiliation),
        _resolve_model(settings),
        int(settings["max_results"]),
        "stage1",
    ]
    return json.dumps(parts, ensure_ascii=True, separators=(",", ":"))


def _get_cached_stage1(cache: Mapping[str, Any], key: str) -> Optional[Dict[str, Any]]:
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


def _store_stage1_cache(
    cache: Dict[str, Any],
    key: str,
    content: str,
    statuses: Dict[str, Optional[str]],
    citations: List[str],
) -> None:
    entries = cache.setdefault("entries", {})
    if not isinstance(entries, dict):
        cache["entries"] = {}
        entries = cache["entries"]
    entries[key] = {
        "timestamp": time.time(),
        "raw_text": content,
        "statuses": statuses,
        "citations": citations,
    }


def _read_openrouter_settings(config: Mapping[str, Any]) -> Dict[str, Any]:
    section = config.get("openrouter_web_search")
    if not isinstance(section, dict):
        raise ValueError("Missing 'openrouter_web_search' section in config/llm_model.yaml")

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
        raise ValueError("Missing openrouter_web_search.model in config/llm_model.yaml")
    if not api_key:
        raise ValueError("Missing OpenRouter API key; set openrouter_web_search.api_key or env")

    web_search_mode = section.get("web_search_mode") or "plugins"
    if isinstance(web_search_mode, str):
        web_search_mode = web_search_mode.strip().lower()
    if web_search_mode not in ("plugins", "online"):
        raise ValueError("web_search_mode must be 'plugins' or 'online'")

    max_results = _coerce_int(section.get("max_results"), default=2)
    timeout_s = _coerce_int(section.get("timeout_s"), default=25)
    max_retries = _coerce_int(section.get("max_retries"), default=0)

    return {
        "model": str(model),
        "api_base": str(api_base).rstrip("/"),
        "api_key": str(api_key),
        "api_key_env": str(api_key_env),
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
    retries = max(0, int(max_retries))
    total_attempts = retries + 1
    for attempt in range(total_attempts):
        try:
            req = urllib.request.Request(url, data=data, headers=dict(headers), method="POST")
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            last_err = RuntimeError(f"HTTP {e.code}: {body or e.reason}")
        except Exception as e:  # demo script: unify error handling
            last_err = e

        if attempt < total_attempts - 1:
            time.sleep(0.6 * attempt)

    raise RuntimeError(f"HTTP request failed after retries: {last_err}")


def _call_openrouter_chat(prompt: str, settings: Mapping[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    model = _resolve_model(settings)
    web_search_mode = settings["web_search_mode"]

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if web_search_mode == "plugins":
        payload["plugins"] = [{"id": "web", "max_results": settings["max_results"]}]

    url = f"{settings['api_base']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
        "User-Agent": "PaperCitedRemarkAnalysis/OpenRouterWebSearchDemo",
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


def _render_citations(annotations: Iterable[Mapping[str, Any]]) -> List[str]:
    lines: List[str] = []
    for ann in annotations:
        if ann.get("type") != "url_citation":
            continue
        citation = ann.get("url_citation") or {}
        if not isinstance(citation, dict):
            continue
        url = citation.get("url")
        title = citation.get("title") or ""
        if isinstance(url, str) and url:
            label = title if isinstance(title, str) and title.strip() else url
            lines.append(f"- {label} ({url})")
    return lines


def _parse_query_arg(query: str) -> Tuple[Optional[str], Optional[str]]:
    if not query:
        return None, None
    parts = re.split(r"\s{2,}", query.strip(), maxsplit=1)
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def _print_block(title: str, content: str, citations: List[str]) -> None:
    sep = "=" * 70
    print(sep)
    print(title)
    print(sep)
    print(content.strip() if content else "(empty)")
    if citations:
        print("\nCitations:")
        for line in citations:
            print(line)
    print("")


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenRouter web-search demo for scholar honor lookup.")
    parser.add_argument("--name", help="Scholar name")
    parser.add_argument("--affiliation", help="Affiliation")
    parser.add_argument(
        "--query",
        help="Single string; use 2+ spaces to separate name and affiliation",
    )
    parser.add_argument(
        "--stage2",
        choices=("auto", "always", "never"),
        default="never",  # Stage 2 is high latency; enable explicitly.
        help="Whether to run the fallback discovery stage",
    )
    parser.add_argument("--max-results", type=int, default=None, help="Override max web results")
    parser.add_argument("--timeout", type=int, default=None, help="Override request timeout")

    args = parser.parse_args()

    name, affiliation = args.name, args.affiliation
    if args.query:
        parsed_name, parsed_affil = _parse_query_arg(args.query)
        if parsed_name:
            name = name or parsed_name
        if parsed_affil:
            affiliation = affiliation or parsed_affil

    if not name:
        print("Error: missing scholar name. Provide --name or --query.", file=sys.stderr)
        raise SystemExit(2)

    config_path = Path(__file__).resolve().parents[2] / "config" / "llm_model.yaml"
    config = _load_yaml(config_path)
    settings = _read_openrouter_settings(config)

    if args.max_results is not None:
        settings = dict(settings)
        settings["max_results"] = args.max_results
    if args.timeout is not None:
        settings = dict(settings)
        settings["timeout_s"] = args.timeout

    affiliation_text = affiliation or "Unknown"
    prompt1 = PROMPT_HONOR_CHECK.format(name=name, affiliation=affiliation_text)
    cache_path = _cache_path()
    cache = _load_cache(cache_path)
    cache_key = _make_cache_key(name, affiliation_text, settings)
    cached = _get_cached_stage1(cache, cache_key)
    if cached:
        cached_content = cached.get("raw_text")
        content1 = cached_content if isinstance(cached_content, str) else ""
        cached_citations = cached.get("citations")
        if isinstance(cached_citations, list):
            citations1 = [c for c in cached_citations if isinstance(c, str)]
        else:
            citations1 = []
        cached_statuses = cached.get("statuses")
        if isinstance(cached_statuses, dict):
            statuses = {
                str(k): (str(v).capitalize() if isinstance(v, str) else None)
                for k, v in cached_statuses.items()
            }
        else:
            statuses = _parse_honor_statuses(content1)
    else:
        content1, annotations1 = _call_openrouter_chat(prompt1, settings)
        citations1 = _render_citations(annotations1)
        statuses = _parse_honor_statuses(content1)
        _store_stage1_cache(cache, cache_key, content1, statuses, citations1)
        _save_cache(cache_path, cache)

    _print_block("Stage 1: Honor Check", content1, citations1)
    any_yes = any(status == "Yes" for status in statuses.values() if status)
    if statuses:
        print("Parsed statuses:")
        for org in HONOR_ORGS:
            status = statuses.get(org) or "Unparsed"
            print(f"- {org}: {status}")
        print("")

    run_stage2 = args.stage2 == "always" or (args.stage2 == "auto" and not any_yes)
    if not run_stage2:
        if args.stage2 == "never":
            print("Stage 2 skipped (disabled; enable explicitly).")
        else:
            print("Stage 2 skipped (at least one Fellow honor confirmed).")
        return

    prompt2 = PROMPT_FALLBACK_DISCOVERY.format(name=name, affiliation=affiliation_text)
    content2, annotations2 = _call_openrouter_chat(prompt2, settings)
    _print_block("Stage 2: Fallback Honor Discovery", content2, _render_citations(annotations2))


if __name__ == "__main__":
    main()
