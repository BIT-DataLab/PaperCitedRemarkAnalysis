from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from openai import OpenAI


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
        if (
            len(value) >= 2
            and value[0] in ("'", '"')
            and value[-1] == value[0]
        ):
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


def _read_text_llm_settings(config: Dict[str, Any]) -> Tuple[str, str, str]:
    text_cfg = config.get("text")
    settings: Dict[str, Any]
    if isinstance(text_cfg, dict) and text_cfg:
        settings = text_cfg
    else:
        settings = config

    model = settings.get("model")
    base_url = settings.get("base_url") or settings.get("api_base")
    api_key = settings.get("api_key")

    missing = [
        name
        for name, value in (("model", model), ("base_url/api_base", base_url), ("api_key", api_key))
        if not value
    ]
    if missing:
        raise ValueError(f"Missing config fields: {', '.join(missing)}")

    return str(model), str(base_url), str(api_key)


def main() -> None:
    config_path = Path(__file__).with_name("llm_model.yaml")
    config = _load_llm_config(config_path)
    model, base_url, api_key = _read_text_llm_settings(config)

    client = OpenAI(base_url=base_url, api_key=api_key)

    completion = client.chat.completions.create(
        # extra_headers={
        #   "HTTP-Referer": "<YOUR_SITE_URL>", # Optional. Site URL for rankings on openrouter.ai.
        #   "X-Title": "<YOUR_SITE_NAME>", # Optional. Site title for rankings on openrouter.ai.
        # },
        extra_body={},
        model=model,
        messages=[
            {
                "role": "user",
                "content": "What is the meaning of life?",
            }
        ],
    )
    print(completion.choices[0].message.content)


if __name__ == "__main__":
    main()
