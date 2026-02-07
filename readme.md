---
title: PaperCitedRemarkAnalysis
version: v1
status: draft
---

# PaperCitedRemarkAnalysis

End-to-end pipeline to analyze how influential citations (Fellow authors) refer to a target paper.
Given a target paper title, the system pulls citing papers, filters for published works,
checks Fellow status for top authors, extracts citation contexts from PDFs, scores each
context with an LLM, and outputs reports plus trace logs for reproducibility.

## Pipeline (T1-T9)

1. RunContext init and parameter snapshot (run_id, dirs, trace)
2. OpenAlex title match (target paper id/doi)
3. Cited-by pull (TopK)
4. DBLP publication check (keep published)
5. Author metrics enrich (h-index, institutions)
6. Fellow check for TopK authors (IEEE/ACM/AAAI)
7. Candidate selection with fallback (max h-index)
8. PDF download -> fulltext extraction -> citation context extraction
9. LLM scoring + per-paper report + summary report

## Quickstart

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the single-paper pipeline:

```bash
python pipeline_test/e2e_single_paper_citation_analysis.py \
  --paper-to-analyze "Database Meets Artificial Intelligence: A Survey" \
  --llm-config-path config/llm_model.yaml \
  --res-dir trace_log/db_ai_survey/res \
  --log-dir trace_log/db_ai_survey/log \
  --target-author "Chengliang Chai"
```

Dry-run (skip LLM calls):

```bash
python pipeline_test/e2e_single_paper_citation_analysis.py \
  --paper-to-analyze "Database Meets Artificial Intelligence: A Survey" \
  --llm-config-path config/llm_model.yaml \
  --res-dir trace_log/db_ai_survey/res \
  --log-dir trace_log/db_ai_survey/log \
  --dry-run
```

## 单篇论文输出结果和日志

Under `trace_log/<target_paper_name>/res`:

- `paper_ref_contexts/{paper_id}.json` (PDF/fulltext/ref_ctx)
- `paper_ref_contexts_scored/{paper_id}.json` (LLM scores)
- `fulltext/{paper_id}.md`
- `pdf/{paper_id}.pdf`
- `reports/paper/{paper_id}.md`
- `reports/summary.md`
- `summary.json`

Under `trace_log/<target_paper_name>/log`:

- `{run_id}.ndjson` (stage trace logs)


