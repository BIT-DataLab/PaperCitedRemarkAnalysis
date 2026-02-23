

## Sheet1：单篇目标论文大佬情况概述（1 行 = 1 篇目标论文）

**核心目标**：一眼看出“这篇目标论文是否被大佬引用、被哪些 citing papers 的哪些大佬引用、是否有 Fellow”。

建议字段（尽量精简但够用）：

1. **target_paper_title** (str)

   * 目标论文标题（来自 `paper_to_analyze.query_title`）
2. **target_paper_id** (str)

   * 目标论文 OpenAlex/内部 paper_id（`paper_to_analyze.paper_id`）
3. **generated_at** (str/datetime)

   * 本次 summary 生成时间（`generated_at`）
4. **citing_paper_count** (int)

   * citing paper 总数（`len(cited_paper_remarks)`）
5. **citing_context_count** (int)

   * 总引用上下文条数（对所有 citing papers 的 `len(contexts)` 求和；没有 PDF 的 contexts 为空）
6. **citing_paper_with_context_count** (int)

   * 有 context 的 citing paper 数（`len(contexts) > 0`）
7. **citing_paper_no_context_count** (int)

   * 无 context 的 citing paper 数（保留“拿不到 pdf/无法抽取”的占位统计）
8. **has_any_fellow** (bool)

   * 是否存在 `has_fellow_topk == True` 的 citing paper（你要的“有没有 fellow”总开关）
9. **citing_papers_all_agg** (str)

   * **聚合字段 1：所有 citing papers + 其 topk_authors 信息**
   * 建议格式（单字段可读）：

     * `"{paper_title} [SEP] venue={venue} [SEP] fellow={has_fellow_topk} [SEP] topk_authors=[Name(h_index=, ieee=, acm=, aaai=); ...]"`
   * 说明：`[SEP]` 是字段分隔符，避免在 Markdown 表格中使用 `|` 导致列解析错误。

10. **citing_papers_fellow_agg** (str)

* **聚合字段 2：仅 Fellow citing papers + 作者信息**（筛 `has_fellow_topk==True`）

> 你说“直观看出哪些论文被大佬引用了，是哪些 citing papers 中的大佬引用的”：
>
> * `has_any_fellow` + `citing_papers_fellow_agg` 最直观；
> * `citing_papers_all_agg` 用于完整回溯与检索。

---

## Sheet2：所有目标论文的引文分析（1 行 = 1 条引用 context；无 context 的 citing paper 也要占 1 行）

**核心目标**：每条引用上下文都能追溯：目标论文、citing paper、作者（topk）、entry、context、LLM 评价。

建议字段：

1. **target_paper_title** (str)
2. **target_paper_id** (str)
3. **citing_paper_title** (str)（`cited_paper_remarks.paper_title`）
4. **citing_paper_venue** (str)（`venue`）
5. **citing_self_citation** (bool)（`self_citation`）
6. **citing_has_fellow_topk** (bool)（`has_fellow_topk`）
7. **citing_topk_authors_str** (str)

   * 便于人读的作者串：
   * `Name(h_index, affiliation, fellow_status.ieee/acm/aaai) ; ...` 
8. **citing_topk_authors_json** (str)

   * 把 `topk_authors` 原样 JSON dump（用于后续程序再加工/过滤）
9. **reference_entry** (str)

   * 目标论文在 citing paper 里的参考文献 entry（`reference_entry`，可能为 null）
10. **context_index** (int)

* 该 citing paper 下的第几条 context（从 0 开始）；如果 citing paper 没有 context，则填 `0`（固定占位）

11. **context_text** (str)

* 引用上下文正文；如果拿不到 pdf / contexts 为空，则写字符串 `"None"`（按你的要求）

12. **remark_score** (int/None)

* LLM 评价分数（`remark_score`）；无 context 时置空

13. **remark_reason** (str/None)

* LLM 给出的评价原因（`reason`）；无 context 时置空

14. 
> * **row_type**：`"has_context"` / `"no_context"`（方便 Excel 里筛掉 no_context 或单独统计）


* Sheet1：按 target paper 聚合 citing papers（拼两列 agg 字符串）；
* Sheet2：展开 contexts；若 contexts 为空，为该 citing paper 造 1 条占位行（`context_text="None"`）。
