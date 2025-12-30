
# llm 评价分析需求
需要用llm对提取出的ref_contexts进行引用评价评分（基于评分，不做正/中/负分类输出）：
@log/e2e_ref_ctx_get_run/paper_ref_contexts中每篇论文 
比如log/e2e_ref_ctx_get_run/paper_ref_contexts/W4402715937.json中的
对"ref_ctx"字段下的每一个"contexts"条目进行remark评价，remark越积极，评分越高：

- 输出字段：`remark_score`（int, 0-10）和`reason`（简要理由）
- 统计解释建议：0-3 偏负面，4-6 中性/不明确，7-10 偏正面

需要用LLM对之前引用上下文的识别结果中（由 @smoke_test/e2e_ref_ctx_get_smoke_test.py 生成）的context进行识别分析，比如W4402715937.json，
然后生成逐论文的引文评价报告，最后针对所有的引文搞一个总体的报告

# 端到端评价分析 pipeline要求
我需要你在 @pipeline_test/e2e_ref_ctx_get_and_remark_analy.py 中写出针对一篇论文的端到端的引文上下文获取和评价分析的pipeline代码。
