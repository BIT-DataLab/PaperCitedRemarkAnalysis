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