"""LLM configuration helpers for remark analysis."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union


@dataclass(frozen=True)
class LLMConfig:
    model: str
    base_url: str
    api_key: str
    temperature: float = 0.0
    max_tokens: int = 256
    timeout_s: int = 60
    json_mode: bool = True


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_config_path() -> Path:
    return _repo_root() / "ref_code" / "chat_llm" / "llm_model.yaml"


def _load_minimal_yaml(path: Path) -> Dict[str, Any]:
    """A tiny YAML loader for simple 'section: {k: v}' configs (no lists)."""
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


def _load_llm_config(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        return _load_minimal_yaml(path)

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML root type: {type(data)!r}")
    return data


def _read_text_llm_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    text_cfg = config.get("text")
    settings: Dict[str, Any]
    if isinstance(text_cfg, dict) and text_cfg:
        settings = text_cfg
    else:
        settings = config

    return settings


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return default


def load_llm_config(config_path: Optional[Union[str, Path]] = None) -> LLMConfig:
    """Load LLM config with env overrides.

    Env overrides:
      - PCRA_LLM_MODEL
      - PCRA_LLM_BASE_URL
      - PCRA_LLM_API_KEY
      - PCRA_LLM_TEMPERATURE
      - PCRA_LLM_MAX_TOKENS
      - PCRA_LLM_TIMEOUT
      - PCRA_LLM_JSON_MODE
    """

    config_path = Path(config_path) if config_path else _default_config_path()
    config = _load_llm_config(config_path) if config_path.exists() else {}
    settings = _read_text_llm_settings(config)

    model = os.getenv("PCRA_LLM_MODEL") or settings.get("model")
    base_url = os.getenv("PCRA_LLM_BASE_URL") or settings.get("base_url") or settings.get("api_base")
    api_key = os.getenv("PCRA_LLM_API_KEY") or settings.get("api_key")

    if not model or not base_url or not api_key:
        missing = [
            name
            for name, value in (("model", model), ("base_url", base_url), ("api_key", api_key))
            if not value
        ]
        raise ValueError(f"Missing LLM config fields: {', '.join(missing)}")

    temperature = float(os.getenv("PCRA_LLM_TEMPERATURE") or settings.get("temperature") or 0.0)
    max_tokens = int(os.getenv("PCRA_LLM_MAX_TOKENS") or settings.get("max_tokens") or 256)
    timeout_default = settings.get("timeout")
    timeout_s = _env_int("PCRA_LLM_TIMEOUT", int(timeout_default) if timeout_default else 60)
    json_mode = _env_bool("PCRA_LLM_JSON_MODE", _parse_bool(settings.get("json_mode"), True))

    return LLMConfig(
        model=str(model),
        base_url=str(base_url),
        api_key=str(api_key),
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
        json_mode=json_mode,
    )
