"""LLM scorer for citation remark analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import md5
from typing import Any, Dict, Optional

from .config import LLMConfig

PROMPT_VERSION = "v1"


@dataclass(frozen=True)
class RemarkResult:
    remark_score: int
    reason: str
    error: Optional[str] = None


def _build_messages(payload: Dict[str, str]) -> list[Dict[str, str]]:
    system = (
        "You evaluate the citation sentiment strength toward the target paper. "
        "Return only a JSON object with remark_score (0-10 int) and reason."
    )
    user = (
        "Score the citation sentiment toward the target paper using the context.\n"
        "Scoring rules:\n"
        "0-3: negative or critical\n"
        "4-6: neutral or unclear/background\n"
        "7-10: positive or supportive\n"
        "Return only JSON: {\"remark_score\": int, \"reason\": \"...\"}\n"
        f"Target title: {payload.get('target_title','')}\n"
        f"Reference entry: {payload.get('reference_entry','')}\n"
        f"Citation marker: {payload.get('citation_marker','')}\n"
        f"Citing paper: {payload.get('citing_paper_title','')}\n"
        f"Context: {payload.get('context','')}\n"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_json_from_text(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        snippet = text[start : end + 1]
        return json.loads(snippet)
    raise ValueError("JSON parse failed")


def _coerce_score(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("Invalid remark_score type")
    if isinstance(value, (int, float)):
        score = int(round(float(value)))
    elif isinstance(value, str):
        score = int(round(float(value.strip())))
    else:
        raise ValueError("Invalid remark_score type")

    if score < 0:
        score = 0
    if score > 10:
        score = 10
    return score


def _mock_score(seed: str) -> int:
    digest = md5(seed.encode("utf-8")).hexdigest()
    return int(digest[:2], 16) % 11


def _call_openai(
    config: LLMConfig,
    messages: list[Dict[str, str]],
    *,
    client: Optional[Any] = None,
) -> str:
    try:
        from openai import OpenAI  # type: ignore
    except ModuleNotFoundError as e:
        raise RuntimeError("openai package is required for LLM scoring") from e

    if client is None:
        client = OpenAI(base_url=config.base_url, api_key=config.api_key, timeout=config.timeout_s)

    params: Dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    if config.json_mode:
        params["response_format"] = {"type": "json_object"}
    try:
        completion = client.chat.completions.create(**params)
    except Exception:
        if config.json_mode:
            params.pop("response_format", None)
            completion = client.chat.completions.create(**params)
        else:
            raise

    message = completion.choices[0].message
    return message.content or ""


def score_context(
    payload: Dict[str, str],
    *,
    config: Optional[LLMConfig] = None,
    client: Optional[Any] = None,
    dry_run: bool = False,
    max_retries: int = 2,
) -> RemarkResult:
    if dry_run:
        seed = f"{payload.get('target_title','')}|{payload.get('context','')}"
        score = _mock_score(seed)
        return RemarkResult(remark_score=score, reason="dry-run placeholder")

    if config is None:
        raise ValueError("LLM config is required when dry_run is False")

    messages = _build_messages(payload)
    last_error: Optional[str] = None

    for _ in range(max_retries + 1):
        try:
            text = _call_openai(config, messages, client=client)
            data = _parse_json_from_text(text)
            score = _coerce_score(data.get("remark_score"))
            reason = str(data.get("reason") or "").strip()
            if not reason:
                raise ValueError("Empty reason")
            return RemarkResult(remark_score=score, reason=reason)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"

    return RemarkResult(
        remark_score=5,
        reason="scoring failed; fallback neutral",
        error=last_error,
    )
