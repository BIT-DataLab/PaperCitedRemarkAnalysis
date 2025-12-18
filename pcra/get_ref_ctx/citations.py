"""In-text citation bracket matching and context extraction."""

from __future__ import annotations

import re
from typing import List, Tuple

from . import config
from .models import CitationContext


def _line_col(text: str, idx: int) -> Tuple[int, int]:
    line = text.count("\n", 0, idx) + 1
    last_nl = text.rfind("\n", 0, idx)
    col = idx + 1 if last_nl < 0 else (idx - last_nl)
    return line, col


_RANGE_RE = re.compile(r"^(\d+)\s*[–−-]\s*(\d+)$")


def _citation_inner_includes_id(inner: str, target_id: int) -> bool:
    for part in re.split(r"[;,]", inner):
        part = part.strip()
        if not part:
            continue

        m = _RANGE_RE.match(part)
        if m:
            lo = int(m.group(1))
            hi = int(m.group(2))
            if lo <= target_id <= hi or hi <= target_id <= lo:
                return True
            continue

        if part.isdigit() and int(part) == target_id:
            return True
    return False


def extract_citation_contexts(
    body_text: str,
    ref_id: int,
    *,
    window: int,
) -> List[CitationContext]:
    """Find all in-text numeric citation brackets that include ref_id and extract contexts."""

    contexts: List[CitationContext] = []
    for m in config.CITATION_BRACKET_RE.finditer(body_text):
        inner = m.group(1)
        if not _citation_inner_includes_id(inner, ref_id):
            continue

        start, end = m.span()
        ctx_start = max(0, start - window)
        ctx_end = min(len(body_text), end + window)
        line, col = _line_col(body_text, start)

        contexts.append(
            CitationContext(
                ref_id=ref_id,
                match_text=body_text[start:end],
                start=start,
                end=end,
                line=line,
                col=col,
                context=body_text[ctx_start:ctx_end],
            )
        )
    return contexts
