我需要将当前的pcra中的模块组装到一起，进行一个端到端的测试：

```
这个测试会输入一篇{paper_to_analy}， 要求利用这些模块执行下面的流程：
- 找出引用了{paper_to_analy}的论文列表cited_by
- 取其中的被引用数最高的{topk_citation_cand}篇论文作为cand_citation_cited_by (这一步可以直接在拉取列表时向api给出排序要求)
- 按照论文所有作者的h_index的最大值对cand_citation_cited_by排序，取前{topk_author_max_h_index_cand}个，作为cand_h_index_cited_by
- cand_h_index_cited_by中的每篇论文的所有作者的h_index的最大值 和 被引用数记录到json文件中。
- 进行引用分析，对cand_h_index_cited_by中的每篇论文，找到{paper_to_analy} 在其中的引用位置，分别保存这些context到json文件中(每篇论文存1个)
```

端到端测试的功能函数可以写在 @pcra/pipelines/ 中， 最终给用户手动测试的脚本应该放到 @smoke_test/中

请你分析一下系统当前 @pcra/ 中的模块架构 ， 说明为了实现上述流程，有哪些功能有缺失，然后给出一个模块功能升级计划供我审阅。

---

# Phase 1（已实现）：端到端组装与落盘

## 实现位置

- 业务编排函数：`pcra/pipelines/e2e_ref_ctx_get.py::run_e2e_ref_ctx_get`
- 手动 smoke test 脚本：`smoke_test/e2e_ref_ctx_get_smoke_test.py`

## 使用方法（手动跑 E2E）

```bash
python3 smoke_test/e2e_ref_ctx_get_smoke_test.py \
  "{paper_to_analy}" \
  --topk-citation-cand {topk_citation_cand} \
  --topk-author-max-h-index-cand {topk_author_max_h_index_cand} \
  --out-dir log/e2e_ref_ctx_get_run
```

常用可选参数：
- `--fulltext-method pymupdfllm|pymupdf|mineru`
- `--max-pages 20` / `--no-truncate`
- `--threshold 0.8`（References 匹配阈值）
- `--window 512`（上下文截取窗口）

## 输出（满足 Phase 1 的两个 JSON 产物）

1) 候选集合指标（max(h_index) + cited_by_count）：
- `log/e2e_ref_ctx_get_run/cand_h_index_cited_by.json`

2) 每篇 citing paper 一份引用上下文 JSON：
- `log/e2e_ref_ctx_get_run/paper_ref_contexts/{paper_id}.json`

同时为了便于排查，会把每篇候选的抽取全文写到：
- `log/e2e_ref_ctx_get_run/fulltext/{paper_id}.md`

## 已知限制（当前模块能力边界）

- `pcra/get_ref_ctx` 当前只支持英文 `References/Bibliography` 标题行 + 数字引用格式 `[n]`（不支持 author-year）。
- PDF 获取依赖 DuckDuckGo+Selenium，命中率受网页结构影响；失败会在 `{paper_id}.json` 里记录 `pdf.error/fulltext.error`，但不会中断整个流程。


# 模块功能升级计划（已审阅）

Phase 1（最小可用，先产出你要的 JSON）：在 pcra.pipelines 下新增一个 e2e 组合函数，串起 work_match_by_title -> work_cited_by(topk_citation_cand) -> enrich_authors_with_h_index -> 计算/排序 max_author_h_index 并截断(topk_author_max_h_index_cand) -> 写 metrics.json -> 循环执行 get_pdf/get_pdf_fulltext/get_paper_reference_context 并写 contexts/<paper_id>.json（失败也产出带 error 的 JSON，整体不中断）。

Phase 1 同步：在 smoke_test 下新增手动脚本（CLI），把 paper_to_analy/topk/pdf_method/window/threshold/out_dir 参数化，并输出 summary（成功数、失败数、失败原因分布）。

Phase 2（降低 PDF 获取失败率 + 重复跑成本）：优先用 OpenAlex work_meta 的 open-access URL/landing page 解析 PDF（失败再走 DuckDuckGo），并对下载/抽全文做缓存（按 paper_id 命名，避免标题冲突）。


# E2E测试参数要求
为了防止截断pdf正文的References，我认为对pdf调用pcra/get_pdf_fulltext时 max_pages 要设置为30

我们取实例化参数如下：
paper_to_analy = "Direct Preference Optimization: Your Language Model is Secretly a Reward Model"
topk_citation_cand = 15
topk_author_max_h_index_cand = 6
