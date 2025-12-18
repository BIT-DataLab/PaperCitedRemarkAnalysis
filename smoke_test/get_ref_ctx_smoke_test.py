"""Smoke test: extract in-text citation contexts by reference title.

Example:
  /data/QUEST/jzshe/miniconda3/envs/rag-any/bin/python smoke_test/get_ref_ctx_smoke_test.py \
    downloads/HippoRAG_fulltext.md \
    --title "Learning to retrieve reasoning paths over wikipedia graph for question answering" \
    --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pcra.get_ref_ctx import get_paper_reference_context


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for pcra.get_ref_ctx (Module 5).")
    parser.add_argument("text", help="Extracted paper text path (Markdown or plain text).")
    parser.add_argument("--title", required=True, help="Target referenced paper title to match in References.")
    parser.add_argument("--window", type=int, default=512, help="Context window size on each side (chars).")
    parser.add_argument("--threshold", type=float, default=0.8, help="Title match threshold (0..1).")
    parser.add_argument("--json", action="store_true", help="Print full result as JSON (includes contexts).")
    parser.add_argument("--max-contexts", type=int, default=5, help="Max contexts to print in text mode.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    text_path = Path(args.text).expanduser()
    if not text_path.exists():
        raise SystemExit(f"Text not found: {text_path}")

    md_text = text_path.read_text(encoding="utf-8", errors="replace")
    result = get_paper_reference_context(
        md_text,
        args.title,
        window=args.window,
        match_threshold=args.threshold,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(0 if result.get("ref_id") else 1)

    if result.get("error"):
        print(result["error"])
        raise SystemExit(1)

    ref_id = result.get("ref_id")
    if not isinstance(ref_id, int):
        print(f'No reference entry matched for title: "{args.title}"')
        raise SystemExit(1)

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

