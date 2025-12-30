"""Smoke test: author-year citation contexts by reference title.

Example:
# 针对 (author, year)形式的引用识别测试
/data/QUEST/jzshe/miniconda3/envs/rag-any/bin/python smoke_test/get_ref_ctx_author_year_smoke_test.py --json

# 针对 [id] 形式的引用识别测试
/data/QUEST/jzshe/miniconda3/envs/rag-any/bin/python  smoke_test/get_ref_ctx_smoke_test.py downloads/HippoRAG_fulltext.md --title "Learning to retrieve reasoning paths over wikipedia graph for question answering" --json

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

DEFAULT_FIXTURE = _REPO_ROOT / "smoke_test" / "fixtures" / "author_year_sample.md"
DEFAULT_TITLE = "TacticZero: Learning to Prove Theorems from Scratch with Deep Reinforcement Learning"


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for author-year citations in pcra.get_ref_ctx.")
    parser.add_argument(
        "--text",
        default=str(DEFAULT_FIXTURE),
        help=f"Extracted paper text path (default: {DEFAULT_FIXTURE}).",
    )
    parser.add_argument("--title", default=DEFAULT_TITLE, help="Target referenced paper title to match.")
    parser.add_argument("--window", type=int, default=256, help="Context window size on each side (chars).")
    parser.add_argument("--threshold", type=float, default=0.6, help="Title match threshold (0..1).")
    parser.add_argument(
        "--style",
        default="auto",
        choices=["auto", "numeric", "author_year"],
        help="Citation style selector.",
    )
    parser.add_argument("--json", action="store_true", help="Print full result as JSON (includes contexts).")
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
        citation_style=args.style,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(0 if result.get("ref_id") else 1)

    if result.get("error"):
        print(result["error"])
        raise SystemExit(1)

    if not result.get("ref_id"):
        print(f'No reference entry matched for title: "{args.title}"')
        raise SystemExit(1)

    key = (result.get("author_year_key") or "").lower()
    if "wu" not in key or "2021a" not in key:
        print(f"Unexpected author_year_key: {result.get('author_year_key')}")
        raise SystemExit(1)

    contexts = result.get("contexts") or []
    if not contexts:
        print("No in-text citation contexts found.")
        raise SystemExit(1)

    style = result.get("citation_style_detected")
    if style not in {"author_year", "mixed"}:
        print(f"Unexpected citation_style_detected: {style}")
        raise SystemExit(1)

    has_expected = any(
        ("2021a" in (c.get("match_text") or "")) or ("Wu" in (c.get("match_text") or ""))
        for c in contexts
    )
    if not has_expected:
        print("No author-year citation match_text includes expected tokens.")
        raise SystemExit(1)

    print(f"Matched ref_id: [{result.get('ref_id')}]  score={result.get('match_score')}")
    print(f"author_year_key: {result.get('author_year_key')}")
    print(f"Found {len(contexts)} in-text citation match(es).")


if __name__ == "__main__":
    main()
