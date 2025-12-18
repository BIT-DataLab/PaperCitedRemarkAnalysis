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

