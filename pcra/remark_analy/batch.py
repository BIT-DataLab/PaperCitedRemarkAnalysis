"""Batch scorer for a single paper reference-context JSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .config import LLMConfig
from .scorer import PROMPT_VERSION, score_context

JsonDict = Dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: JsonDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _context_payload(data: JsonDict, ctx: JsonDict) -> Dict[str, str]:
    ref_ctx = data.get("ref_ctx") or {}
    citing = data.get("citing_paper") or {}
    return {
        "target_title": str(ref_ctx.get("query_title") or ""),
        "reference_entry": str(ref_ctx.get("reference_entry") or ""),
        "citation_marker": str(ctx.get("match_text") or ""),
        "citing_paper_title": str(citing.get("paper_title") or ""),
        "context": str(ctx.get("context") or ""),
    }


def _is_scored(ctx: JsonDict) -> bool:
    score = ctx.get("remark_score")
    return isinstance(score, int)


def score_paper_contexts(
    input_path: Path,
    output_path: Path,
    *,
    config: Optional[LLMConfig] = None,
    dry_run: bool = False,
    max_contexts: Optional[int] = None,
    skip_scored: bool = True,
    client: Optional[Any] = None,
) -> JsonDict:
    """Score all contexts in a single Phase-1 paper JSON and write a scored JSON."""

    data: JsonDict = json.loads(Path(input_path).read_text(encoding="utf-8"))
    ref_ctx = data.get("ref_ctx") or {}
    contexts = ref_ctx.get("contexts") or []

    scored = 0
    skipped = 0
    errors = 0
    processed = 0

    for ctx in contexts:
        if max_contexts is not None and processed >= max_contexts:
            break
        processed += 1

        if skip_scored and _is_scored(ctx):
            skipped += 1
            continue

        payload = _context_payload(data, ctx)
        result = score_context(
            payload,
            config=config,
            client=client,
            dry_run=dry_run,
        )
        ctx["remark_score"] = result.remark_score
        ctx["reason"] = result.reason
        if result.error:
            ctx["remark_error"] = result.error
            errors += 1
        scored += 1

    data["remark_analy"] = {
        "generated_at": _utc_now_iso(),
        "prompt_version": PROMPT_VERSION,
        "model": getattr(config, "model", None) if not dry_run else "dry-run",
        "base_url": getattr(config, "base_url", None) if not dry_run else None,
        "scored_count": scored,
        "skipped_count": skipped,
        "error_count": errors,
        "dry_run": dry_run,
    }

    _write_json(output_path, data)
    return {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "contexts_total": len(contexts),
        "contexts_processed": processed,
        "scored": scored,
        "skipped": skipped,
        "errors": errors,
    }
