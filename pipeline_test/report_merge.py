"""Collect summary.json outputs from trace_log into log/merged_summary.

  1. Run python pipeline_test/report_merge.py to generate the merged summaries.
  2. Optionally pass --trace-log-dir or --output-dir to target different locations.

"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]


def _copy_summaries(trace_log_dir: Path, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for summary_path in sorted(trace_log_dir.glob("*/res/summary.json")):
        paper_dir = summary_path.parent.parent.name
        dest_path = output_dir / f"{paper_dir}.json"
        shutil.copy2(summary_path, dest_path)
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge summary.json outputs from trace_log into log/merged_summary."
    )
    parser.add_argument(
        "--trace-log-dir",
        default=str(_REPO_ROOT / "trace_log"),
        help="Directory containing per-paper trace_log folders.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_REPO_ROOT / "log" / "merged_summary"),
        help="Directory for merged summary JSON files.",
    )
    args = parser.parse_args()

    trace_log_dir = Path(args.trace_log_dir)
    if not trace_log_dir.exists():
        print(f"trace_log directory not found: {trace_log_dir}", file=sys.stderr)
        raise SystemExit(1)

    output_dir = Path(args.output_dir)
    count = _copy_summaries(trace_log_dir, output_dir)
    print(f"Copied {count} summary.json files to {output_dir}")


if __name__ == "__main__":
    main()
