# Paper Filter Refactor Plan (Final)

## Goal
- Apply the new multi-level citing paper filter strategy to the flow used by `pipeline_test/e2e_single_paper_citation_analysis.py`.
- Update T3 to dual-recall citing works: topK by citation count plus works published in the most recent K years.
- Add early filters before Fellow lookup: drop papers with authors in `ignore_authors`, and drop papers whose `max_h_index` is below a threshold.
- Keep DBLP publication check and existing selection logic (primary if Fellow found, fallback to topK by max h-index).

## Decisions (Confirmed)
- `pub_year_topk` = recent K years window (all works in that window).
- `ignore_authors` is a list of author names in "GivenName FamilyName" format.
- Name matching uses exact match after normalization: lowercase, trim, remove punctuation (`,` and `.`). Name variants (e.g., `Li, Guoliang`, `G. Li`) are out of scope for v1.
- `max_h_index_thershld` spelling stays as-is.
- Missing `h_index` values are treated as `0`.
- No extra cap after dual recall; keep all works after DBLP + filters.

## Plan
### 1) Parameter surface and wiring
- CLI (`pipeline_test/e2e_single_paper_citation_analysis.py`):
  - `--pub-year-topk` -> `pub_year_topk` (int, recent K years window).
  - `--ignore-authors` -> `ignore_authors` (JSON list string, e.g. `["Guoliang Li","Chengliang Chai"]`).
  - `--max-h-index-thershld` -> `max_h_index_thershld` (int).
- Pipeline (`pcra/pipelines/e2e_single_paper.py`):
  - Extend `run_e2e_single_paper` signature and `params_snapshot` to include the new parameters.
  - Ensure trace `params` captures these inputs in T3/T4b (or a dedicated filter stage if added).

### 2) T3 dual recall (OpenAlex work_cited_by)
- Path A: existing `cited_by_topK` sorted by `cited_by_count:desc,publication_year:desc` (keep current parameter naming).
- Path B: recent years window controlled by `pub_year_topk`:
  - Compute `cutoff_year = current_year - pub_year_topk + 1`.
  - Fetch citing works with `publication_year >= cutoff_year`.
- Merge the two lists with de-duplication by `paper_id`.
  - Attach `recall_sources` per work (e.g., `["top_cited", "recent_year"]`).
  - Trace meta: `top_cited_count`, `recent_year_count`, `deduped_count`, `duplicates_dropped`.

### 3) T3a DBLP publication check (unchanged logic, new input set)
- Apply DBLP publication status validation to the merged citing list.
- Keep `published` only filtering.
- Update trace meta to reflect counts after dual recall.

### 4) T4a metrics enrich + early filters
- Apply `ignore_authors` filter before Fellow lookup:
  - Normalize author names using the same rules as above and drop any work containing a matched ignored author.
  - Track counts in trace meta.
- Enrich author metrics (h-index) for the remaining works.
  - For missing `h_index`, set it to `0` before computing `max_h_index_author`.
- Apply `max_h_index_thershld` filter:
  - Drop any work where `max_h_index_author.h_index < max_h_index_thershld`.
  - Track counts in trace meta.

### 5) T4b Fellow lookup + selection (existing behavior)
- Run Fellow lookup on the remaining works (after filters).
- Keep T4c selection rules: if any Fellow hits, keep all as primary; otherwise fallback to `roll_back_paper_topK`.
- Ensure selection still uses `max_h_index_author` for fallback sorting.

### 6) Trace and output alignment
- Add filter statistics to trace meta for T4b or a new dedicated stage (e.g., `T4b_pre`).
- Surface `recall_sources` and optional `filter_reason` in per-paper payloads for auditability.

### 7) Validation
- Add focused checks:
  - Dual recall de-dup correctness.
  - `ignore_authors` exact match after normalization.
  - `max_h_index_thershld` filtering with missing h-index treated as `0`.
- Run the CLI once with `--dry-run` to confirm counts in trace and expected selection behavior.
