
需要用llm对提取出的ref_contexts进行引用评价评分（基于评分，不做正/中/负分类输出）：
@log/e2e_ref_ctx_get_run/paper_ref_contexts中每篇论文 
比如log/e2e_ref_ctx_get_run/paper_ref_contexts/W4402715937.json中的
对"ref_ctx"字段下的每一个"contexts"条目进行remark评价，remark越积极，评分越高：

- 输出字段：`remark_score`（int, 0-10）和`reason`（简要理由）
- 统计解释建议：0-3 偏负面，4-6 中性/不明确，7-10 偏正面
