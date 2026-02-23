#!/usr/bin/env bash
set -euo pipefail

# conda activate pcraPaper
# User config: update only these three values.
PAPER_TO_ANALYZE="Selective data acquisition in the wild for model charging"
TARGET_AUTHOR="Chengliang Chai"
IGNORE_AUTHORS='["Chengliang Chai","Guoliang Li"]'
RUN_ID="1"
# 手动给论文编号，避免一个论文重复多次。
# Run folder prefix (keep in sync with existing trace_log numbering).


# Fixed config.
LLM_CONFIG_PATH="config/llm_model.yaml"
PUB_YEAR_TOPK=3
MAX_H_INDEX_THRESHOLD=30
CITED_BY_TOPK=20
ROLL_BACK_PAPER_TOPK=5

normalize_title() {
  python - "$1" <<'PY'
import re
import sys

title = sys.argv[1]
normalized = re.sub(r"[^A-Za-z0-9-]+", "_", title)
normalized = re.sub(r"_+", "_", normalized).strip("_")
print(normalized)
PY
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$REPO_ROOT"

NORMALIZED_TITLE="$(normalize_title "$PAPER_TO_ANALYZE")"
if [[ -n "${RUN_ID}" ]]; then
  RUN_TAG="${RUN_ID}_${NORMALIZED_TITLE}"
else
  RUN_TAG="${NORMALIZED_TITLE}"
fi

RES_DIR="trace_log/${RUN_TAG}/res"
LOG_DIR="trace_log/${RUN_TAG}/log"

mkdir -p "$RES_DIR" "$LOG_DIR"

python pipeline_test/e2e_single_paper_citation_analysis.py \
  --paper-to-analyze "$PAPER_TO_ANALYZE" \
  --llm-config-path "$LLM_CONFIG_PATH" \
  --res-dir "$RES_DIR" \
  --log-dir "$LOG_DIR" \
  --target-author "$TARGET_AUTHOR" \
  --ignore-authors "$IGNORE_AUTHORS" \
  --pub-year-topk "$PUB_YEAR_TOPK" \
  --max-h-index-thershld "$MAX_H_INDEX_THRESHOLD" \
  --cited-by-topk "$CITED_BY_TOPK" \
  --roll-back-paper-topk "$ROLL_BACK_PAPER_TOPK"
