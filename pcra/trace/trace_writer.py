"""NDJSON trace writer for pipeline stages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceWriter:
    run_id: str
    trace_path: Path

    @classmethod
    def from_log_dir(cls, run_id: str, log_dir: Path) -> "TraceWriter":
        return cls(run_id=run_id, trace_path=Path(log_dir) / f"{run_id}.ndjson")

    def write(
        self,
        stage_id: str,
        core: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "run_id": self.run_id,
            "stage_id": stage_id,
            "created_at": _utc_now_iso(),
            "core": core or {},
            "params": params or {},
            "meta": meta or {},
        }
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
