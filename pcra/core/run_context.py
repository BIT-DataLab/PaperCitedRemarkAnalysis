"""Run context helpers for the refactored pipeline."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    token = uuid.uuid4().hex[:8]
    return f"{stamp}_{token}"


def _redact_env_value(name: str, value: str) -> str:
    upper = name.upper()
    if any(key in upper for key in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
        return "***"
    return value


def _collect_env(prefixes: Iterable[str]) -> Dict[str, str]:
    env: Dict[str, str] = {}
    for key, value in os.environ.items():
        if any(key.startswith(prefix) for prefix in prefixes):
            env[key] = _redact_env_value(key, value)
    return env


def _coerce_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _coerce_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_coerce_jsonable(v) for v in value]
    return value


@dataclass(frozen=True)
class RunContext:
    run_id: str
    run_started_at: str
    res_dir: Path
    log_dir: Path
    dirs: Dict[str, Path]
    params_frozen: Dict[str, Any]

    @classmethod
    def create(
        cls,
        *,
        paper_to_analyze: str,
        llm_config_path: Optional[str],
        res_dir: str,
        log_dir: str,
        params: Mapping[str, Any],
        env_prefixes: Iterable[str] = ("OPENALEX_", "PCRA_LLM_", "OPENROUTER_"),
        create_dirs: bool = True,
        run_id: Optional[str] = None,
    ) -> "RunContext":
        rid = run_id or _generate_run_id()
        started_at = _utc_now_iso()

        res_root = Path(res_dir).expanduser()
        log_root = Path(log_dir).expanduser()

        dirs = {
            "res_dir": res_root,
            "log_dir": log_root,
            "reports_dir": res_root / "reports",
            "paper_reports_dir": res_root / "reports" / "paper",
            "ref_ctx_dir": res_root / "paper_ref_contexts",
            "ref_ctx_scored_dir": res_root / "paper_ref_contexts_scored",
            "fulltext_dir": res_root / "fulltext",
            "pdf_dir": res_root / "pdf",
            "cache_dir": res_root / "cache",
        }

        if create_dirs:
            for path in dirs.values():
                path.mkdir(parents=True, exist_ok=True)
            log_root.mkdir(parents=True, exist_ok=True)

        params_frozen: Dict[str, Any] = {
            "paper_to_analyze": paper_to_analyze,
            "llm_config_path": llm_config_path,
            "res_dir": str(res_root),
            "log_dir": str(log_root),
            "run_id": rid,
            "run_started_at": started_at,
        }
        params_frozen.update(_coerce_jsonable(dict(params)))
        env = _collect_env(env_prefixes)
        if env:
            params_frozen["env"] = env

        return cls(
            run_id=rid,
            run_started_at=started_at,
            res_dir=res_root,
            log_dir=log_root,
            dirs=dirs,
            params_frozen=params_frozen,
        )
