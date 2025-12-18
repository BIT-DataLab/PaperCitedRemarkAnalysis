"""Extract in-text citation contexts for a referenced paper from PyMuPDF Markdown.

测试方法：
python3 ref_code/get_reference_ctx/get_paper_ref_context.py --json
默认检测的被引用论文title: 
Learning to retrieve reasoning paths over wikipedia graph for question answering

This script is designed for Markdown converted from academic PDFs (e.g. via PyMuPDF4LLM),
where the reference list starts after a standalone line:
  - References / Bibliography
  - **References** / **Bibliography**
  - ## References / ## Bibliography
  - ## **References** / ## **Bibliography**

The reference list contains entries that start with "[id]" (numeric). Given a target
paper title, we:
  1) Locate the References section and match the title to its numeric id.
  2) Search the main body for numeric citation brackets that include that id:
       [id] or [..., id, ...]
  3) For each match, extract +/- N characters as context (default: 512).
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

DEFAULT_MD_PATH = Path(
    "/data2/jproject/PaperCitedRemarkAnalysis/downloads/"
    "HippoRAG_fulltext.md"
)

_REFERENCES_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*\s*(?:References|Bibliography)\s*\*\*|(?:References|Bibliography))\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_REF_ENTRY_START_RE = re.compile(r"^\s*\[(\d+)\]\s+", re.MULTILINE)

# Numeric citation brackets in the main text, e.g.:
#   [4]
#   [36, 42, 66, 87]
#   [16, 100, 54, 14, 4, 44]
_CITATION_BRACKET_RE = re.compile(r"\[\s*(\d(?:[\d\s,;–-]*\d)?)\s*\]")
_RANGE_RE = re.compile(r"^(\d+)\s*[–-]\s*(\d+)$")


@dataclass(frozen=True)
class ReferenceEntry:
    ref_id: int
    raw_text: str


@dataclass(frozen=True)
class CitationContext:
    ref_id: int
    match_text: str
    start: int
    end: int
    line: int
    col: int
    context: str


def _normalize_for_match(text: str) -> str:
    """Lowercase + remove non-alnum (ASCII) for robust title matching."""
    lowered = text.lower()
    lowered = lowered.replace("\u00a0", " ")  # nbsp
    lowered = re.sub(r"[^0-9a-z]+", " ", lowered)
    return " ".join(lowered.split())


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[0-9a-z]+", _normalize_for_match(text))


def _line_col(text: str, idx: int) -> Tuple[int, int]:
    line = text.count("\n", 0, idx) + 1
    last_nl = text.rfind("\n", 0, idx)
    col = idx + 1 if last_nl < 0 else (idx - last_nl)
    return line, col


def split_body_and_references(md_text: str) -> Tuple[str, str]:
    """Split Markdown into (body_text, references_text) by the last References/Bibliography heading."""
    matches = list(_REFERENCES_HEADING_RE.finditer(md_text))
    if not matches:
        raise ValueError(
            'References/Bibliography heading not found (expected a standalone line like '
            '"References", "**References**", "## References", "## **References**", "Bibliography", ...).'
        )
    m = matches[-1]
    body = md_text[: m.start()]
    references = md_text[m.end() :]
    return body, references


def parse_reference_entries(references_text: str) -> List[ReferenceEntry]:
    """Parse numbered reference entries from the References section text."""
    starts = list(_REF_ENTRY_START_RE.finditer(references_text))
    if not starts:
        return []

    entries: List[ReferenceEntry] = []
    for i, m in enumerate(starts):
        ref_id = int(m.group(1))
        start = m.start()
        end = starts[i + 1].start() if i + 1 < len(starts) else len(references_text)
        raw = references_text[start:end].strip()
        entries.append(ReferenceEntry(ref_id=ref_id, raw_text=raw))
    return entries


def _title_match_score(title: str, entry_text: str) -> float:
    """Score how well a title matches a reference entry (0..1)."""
    title_norm = _normalize_for_match(title)
    entry_norm = _normalize_for_match(entry_text)
    if not title_norm:
        return 0.0
    if title_norm in entry_norm:
        return 1.0

    title_tokens = set(_tokenize(title_norm))
    entry_tokens = set(_tokenize(entry_norm))
    if not title_tokens:
        return 0.0
    token_recall = len(title_tokens & entry_tokens) / len(title_tokens)
    seq = SequenceMatcher(None, title_norm, entry_norm).ratio()
    return max(token_recall, seq)


def find_reference_entry_by_title(
    entries: Iterable[ReferenceEntry],
    title: str,
    *,
    match_threshold: float = 0.8,
) -> Optional[Tuple[ReferenceEntry, float]]:
    """Find the best matching reference entry for a given paper title."""
    best: Optional[Tuple[ReferenceEntry, float]] = None
    for e in entries:
        score = _title_match_score(title, e.raw_text)
        if best is None or score > best[1]:
            best = (e, score)
    if best is None or best[1] < match_threshold:
        return None
    return best


def _citation_inner_includes_id(inner: str, target_id: int) -> bool:
    # Split on comma/semicolon (common in numeric citations).
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
    window: int = 512,
) -> List[CitationContext]:
    """Find all in-text numeric citation brackets that include ref_id and extract contexts."""
    contexts: List[CitationContext] = []
    for m in _CITATION_BRACKET_RE.finditer(body_text):
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


def get_paper_reference_context(
    md_text: str,
    title: str,
    *,
    window: int = 512,
    match_threshold: float = 0.8,
) -> dict:
    """High-level API: title -> ref_id -> in-text contexts."""
    body, references = split_body_and_references(md_text)
    entries = parse_reference_entries(references)
    match = find_reference_entry_by_title(entries, title, match_threshold=match_threshold)
    if match is None:
        return {
            "query_title": title,
            "ref_id": None,
            "match_score": 0.0,
            "reference_entry": None,
            "contexts": [],
        }

    entry, score = match
    contexts = extract_citation_contexts(body, entry.ref_id, window=window)
    return {
        "query_title": title,
        "ref_id": entry.ref_id,
        "match_score": score,
        "reference_entry": entry.raw_text,
        "contexts": [
            {
                "ref_id": c.ref_id,
                "match_text": c.match_text,
                "start": c.start,
                "end": c.end,
                "line": c.line,
                "col": c.col,
                "context": c.context,
            }
            for c in contexts
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find where a given paper title is cited in a PyMuPDF-extracted Markdown paper."
    )
    parser.add_argument(
        "--md",
        default=str(DEFAULT_MD_PATH),
        help=f"Markdown path (default: {DEFAULT_MD_PATH}).",
    )
    parser.add_argument(
        "--title",
        default="Learning to retrieve reasoning paths over wikipedia graph for question answering",
        help="Target paper title to match in the References section.",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=512,
        help="Context window size on each side (characters).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.8,
        help="Title match threshold (0..1).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full result as JSON (includes contexts).",
    )
    parser.add_argument(
        "--max-contexts",
        type=int,
        default=20,
        help="Max contexts to print in text mode (default: 20).",
    )
    args = parser.parse_args()

    md_path = Path(args.md).expanduser()
    if not md_path.exists():
        raise SystemExit(f"Markdown not found: {md_path}")

    md_text = md_path.read_text(encoding="utf-8", errors="replace")
    result = get_paper_reference_context(
        md_text,
        args.title,
        window=args.window,
        match_threshold=args.threshold,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return

    ref_id = result.get("ref_id")
    if not isinstance(ref_id, int):
        print(f'No reference entry matched for title: "{args.title}"')
        return

    print(f"Matched ref_id: [{ref_id}]  score={result.get('match_score')}")
    ref_entry = (result.get("reference_entry") or "").strip()
    if ref_entry:
        preview = ref_entry if len(ref_entry) <= 400 else (ref_entry[:400] + " ...")
        print(f"Reference entry: {preview}")
    print()

    contexts = result.get("contexts") or []
    print(f"Found {len(contexts)} in-text citation match(es).")
    for i, c in enumerate(contexts[: max(0, int(args.max_contexts))], start=1):
        print(f"\n--- Match {i}: line {c['line']} col {c['col']}  {c['match_text']}")
        print(c["context"])


if __name__ == "__main__":
    main()
