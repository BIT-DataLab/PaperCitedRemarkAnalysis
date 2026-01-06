# Paper Filter Refactor Plan

## Goal
- Apply the new multi-level citing paper filter strategy to the flow used by `pipeline_test/e2e_single_paper_citation_analysis.py`.
- Update T3 to dual-recall citing works: topK by citation count plus works published in the most recent K years.
- Add early filters before Fellow lookup: drop papers with authors in `ignore_authors`, and drop papers whose `max_h_index` is below a threshold.
- Keep DBLP publication check and existing selection logic (primary if Fellow found, fallback to topK by max h-index).

## Plan
### 1) Parameter surface and wiring
- CLI (`pipeline_test/e2e_single_paper_citation_analysis.py`): add arguments
  - `--pub-year-topk` -> `pub_year_topk`
  - `--ignore-authors` -> `ignore_authors` (format to be decided)
  - `--max-h-index-thershld` -> `max_h_index_thershld`
- Pipeline (`pcra/pipelines/e2e_single_paper.py`):
  - Extend `run_e2e_single_paper` signature and `params_snapshot` to include the new parameters.
  - Ensure trace `params` captures these inputs in T3/T4b (or a dedicated filter stage if added).

### 2) T3 dual recall (OpenAlex work_cited_by)
- Keep existing `cited_by_topK` call sorted by `cited_by_count:desc,publication_year:desc`.
- Add a second recall path for recent years controlled by `pub_year_topk`:
  - Implement a helper in `pcra/openalex/facade.py` (or `pcra/openalex/works.py`) to fetch citing works filtered by `publication_year >= cutoff`.
  - Compute `cutoff_year = current_year - pub_year_topk + 1`.
- Merge the two lists with de-duplication by `paper_id`.
  - Record `recall_sources` per work (for trace/debug).
  - Trace meta: `top_cited_count`, `recent_year_count`, `deduped_count`, `duplicates_dropped`.

### 3) T3a DBLP publication check (unchanged logic, new input set)
- Apply DBLP publication status validation to the merged citing list.
- Keep existing `published` only filtering.
- Update trace meta to reflect counts after dual recall.

### 4) T4a metrics enrich + early filters
- Apply `ignore_authors` filter:
  - Normalize author names (same logic as self-citation) and drop any work containing an ignored name.
  - Track counts in trace meta.
- After `enrich_authors_with_metrics`, compute `max_h_index_author` for each work.
- Apply `max_h_index_thershld` filter:
  - Drop any work where `max_h_index_author.h_index < max_h_index_thershld`.
  - Decide how to handle missing `h_index` values (see uncertainties).

### 5) T4b Fellow lookup + selection (existing behavior)
- Run Fellow lookup on the remaining works (after filters).
- Keep T4c selection rules: if any Fellow hits, keep all as primary; otherwise fallback to `roll_back_paper_topK`.
- Ensure selection still uses `max_h_index_author` for fallback sorting.

### 6) Trace and output alignment
- Add filter statistics to trace meta for T4b or a new dedicated stage (e.g., `T4b_pre`).
- Optionally surface `recall_sources` and `filter_reason` in per-paper payloads for auditability.

### 7) Validation
- Add small unit tests or focused checks:
  - Dual recall de-dup correctness.
  - `ignore_authors` name matching.
  - `max_h_index_thershld` filtering with missing h-index.
- Run the CLI once with `--dry-run` to confirm counts in trace and expected selection behavior.

## Uncertainties
- `pub_year_topk` semantics: is this a "recent K years window" (all works in that window) or "top K most recent works"?
- How should `ignore_authors` be provided and matched: comma-separated names, repeated flags, or JSON list? Exact match vs substring, and do we normalize whitespace/case only?
- `max_h_index_thershld` spelling: keep as-is or rename to `max_h_index_threshold`?
- For missing author h-index values, should the paper be dropped, treated as `0`, or kept?
- Should we cap the total merged candidate count after dual recall, or keep all (post DBLP + filters)?

## Uncertainties answer
- `pub_year_topk` semantics: is a "recent K years window" (all works in that window)

- How should `ignore_authors` be provided and matched: comma-separated names, repeated flags, or JSON list? Exact match vs substring, and do we normalize whitespace/case only?
```python
ignore_authors = [
    "Guoliang Li",
    "Chengliang Chai",
    "Lei Cao",
]
```
**Matching semantics**：

* Author names are provided in **"GivenName FamilyName"** format.
* Before matching, author names from OpenAlex / DBLP / PDF extraction are:

  * lowercased
  * stripped of leading/trailing whitespace
  * normalized by removing punctuation (`, .`)
* Matching is done via **exact match after normalization** (not substring match).
* Name variants (e.g., `Li, Guoliang`, `G. Li`) are **out of scope for v1** and may be addressed in future iterations if needed.



- `max_h_index_thershld` spelling: keep as-is or rename to `max_h_index_threshold`?
保持现状为: `max_h_index_thershld` 

- For missing author h-index values, should the paper be dropped, treated as `0`, or kept?
直接把缺失h_index的author的 h_index设置为 0

- Should we cap the total merged candidate count after dual recall, or keep all (post DBLP + filters)?
不需要额外裁剪，在 DBLP + 各类过滤之后保留全部

