# LLM 引文评价分析模块设计与计划（Phase 2）

## 0. 背景与现状

当前 Phase 1 已能稳定产出“逐引用论文的引用上下文 JSON”（见 `pcra/pipelines/e2e_ref_ctx_get.py`）：

- 候选指标：`log/e2e_ref_ctx_get_run/cand_h_index_cited_by.json`
- 逐 citing paper 引用上下文：`log/e2e_ref_ctx_get_run/paper_ref_contexts/{paper_id}.json`
- 抽取全文（排查用）：`log/e2e_ref_ctx_get_run/fulltext/{paper_id}.md`

本 Phase 2 目标：在 Phase 1 的 `ref_ctx.contexts[]` 基础上，引入 LLM 对每条引用语境进行“引用评价打分”（0-10）并生成报告（逐论文 + 总体）。

---

## 1. 需求解读（来自 `doc/dev/e2e_llm_remark_analy.md`）

### 1.1 输入范围

- 对 `log/e2e_ref_ctx_get_run/paper_ref_contexts/` 目录下每篇论文 JSON：
  - 对 `ref_ctx.contexts[]` 的每个条目进行 LLM 评价分析。

### 1.2 上下文级输出字段（必须）

对每个 `ref_ctx.contexts[]` 条目新增（或在新文件中写出）：

- `remark_score`: `int`，范围 `0..10`（越积极越高）
- `reason`: `str`，简要理由

统计解释建议：
- `0..3` 偏负面
- `4..6` 中性/不明确
- `7..10` 偏正面

### 1.3 报告产出（必须）

- 逐论文（逐 citing paper）引文评价报告
- 所有 citing papers 的总体报告（聚合统计）

### 1.4 端到端 pipeline（必须）

- 在 `pipeline_test/e2e_ref_ctx_get_and_remark_analy.py` 编写“针对一篇论文的端到端：引文上下文获取 + 评价分析”的 pipeline 代码。

---

## 2. 设计目标

### 2.1 功能目标

- 对每条引用上下文产出稳定的 `remark_score/reason`（仅评分，不输出“正/中/负”标签字段）。
- 输出逐论文报告 + 总体报告，支持快速定位“高赞同/高质疑”的引用语境。

### 2.2 兼容性目标

- **不修改** Phase 1 的输出格式与行为（`pcra/pipelines/e2e_ref_ctx_get.py` 保持原样）。
- Phase 2 产物写到新的输出目录（避免覆盖 `paper_ref_contexts/{paper_id}.json`）。

### 2.3 可复跑与成本目标

- 支持断点续跑：已打分的 context 可跳过（按 `remark_score` 是否存在判断）。
- 支持并发/限流配置（避免触发 LLM 限速）。
- 支持 dry-run/mock（无 LLM 时也能跑通报告结构，便于调试流水线）。

### 2.4 可观测性目标

- 对每条 context 记录 LLM 调用失败原因（网络/超时/解析失败），并在报告中给出失败计数。
- 记录 `model/base_url/prompt_version/generated_at` 等元信息，方便复现与对比。

---

## 3. 输入/输出数据结构约定

### 3.1 输入：Phase 1 `paper_ref_contexts/{paper_id}.json`

关键字段（示例见 `log/e2e_ref_ctx_get_run/paper_ref_contexts/W4402715937.json`）：

- `paper_to_analyze`: 目标被引论文信息（title / id / doi）
- `citing_paper`: 引用论文信息（paper_id/title/authors/h-index 等）
- `ref_ctx`:
  - `query_title`: 用于匹配 References 的目标 title
  - `ref_id`: 目标引用编号（数字引用时为 int；未命中时可能为 null）
  - `reference_entry`: References 中命中的条目文本
  - `contexts[]`: 上下文片段列表（每项含 `context/match_text/start/end/line/col/...`）

### 3.2 输出：打分后的逐论文 JSON（建议新增目录）

建议输出目录结构（可在 CLI 中通过 `--out-dir` 指定根目录）：

- `{out_dir}/paper_ref_contexts_scored/{paper_id}.json`：逐论文打分 JSON
- `{out_dir}/reports/paper/{paper_id}.md`：逐论文报告（Markdown）
- `{out_dir}/reports/summary.md` + `{out_dir}/reports/summary.json`：总体报告

逐论文打分 JSON 建议“最小侵入式”扩展：在 `ref_ctx.contexts[]` 的每个 item 上追加字段：

- `remark_score`: int（0..10）
- `reason`: str

并在顶层附带一段元信息（可选但推荐）：

- `remark_analy`: `{generated_at, model, base_url, prompt_version, errors_count, scored_count}`

说明：
- 必须字段仅 `remark_score/reason`；其余字段用于可观测性与复跑对齐。

---

## 4. LLM 评分策略与 Prompt 设计

### 4.1 评分口径（与需求一致）

LLM 要判断“引用语境中对目标论文的态度/评价强度”，并映射为 `0..10`：

- `0..3`：明确质疑/指出缺陷/否定性结论
- `4..6`：背景引用、方法对比、仅陈述事实、态度不明确
- `7..10`：明确认可/采用其方法/强调其贡献/强正面表述

约束：
- **不输出** “positive/neutral/negative” 分类字段；
- `remark_score` 必须是整数；
- `reason` 简短，建议中文（便于汇总阅读），但需准确引用语境信息。

### 4.2 输入给 LLM 的信息（建议）

为了降低“上下文只出现编号 [26]、但没有出现目标论文名称”导致的误判，建议每条 context 给 LLM 提供：

- `target_title`: `ref_ctx.query_title`
- `reference_entry`: `ref_ctx.reference_entry`（含作者/标题/venue/年份）
- `citation_marker`: `contexts[i].match_text`（如 `[26]`）
- `citing_paper_title`: `citing_paper.paper_title`
- `context`: `contexts[i].context`（窗口片段）

### 4.3 输出格式约束（强制）

LLM 输出必须可解析为 JSON 对象：

```json
{"remark_score": 6, "reason": "该处为背景性引用，未给出明确褒贬。"}
```

实现建议：
- 优先使用 OpenAI “JSON mode/结构化输出”能力（若当前 SDK/模型支持）；
- 否则以“只允许输出 JSON”+ 解析失败重试（最多 N 次）作为降级。

---

## 5. 模块与代码组织建议（落地到仓库）

### 5.1 建议新增模块：`pcra/remark_analy/`

目标：把“调用 LLM + 解析 + 断点续跑 + 报告统计”从脚本中拆出来，便于复用。

建议文件职责：

- `pcra/remark_analy/config.py`：读取 `model/base_url/api_key`（优先 env，其次 YAML；避免把 key 写进日志/报告）
- `pcra/remark_analy/scorer.py`：对单条 context 打分（prompt 构造 + LLM 调用 + JSON 解析 + 重试/降级）
- `pcra/remark_analy/batch.py`：对单个 `{paper_id}.json` 做批量打分与落盘（支持跳过已打分条目）
- `pcra/remark_analy/report.py`：逐论文/总体统计与 Markdown 渲染

LLM 配置来源建议：
- 复用 `ref_code/chat_llm/llm_model.yaml` 的字段结构（`text.model/text.api_base/text.api_key`），但 **生产使用优先 env**（避免密钥入库/误提交）。

### 5.2 建议新增 pipeline 编排：`pcra/pipelines/e2e_ref_ctx_get_and_remark_analy.py`

目标：把“Phase 1 引文上下文获取”与“Phase 2 LLM 打分 + 报告生成”串成一个可复用函数：

- 输入：`paper_to_analyze` + Phase 1 参数 + LLM 参数 + out_dir
- 输出：summary（成功数、打分数、失败数、报告路径）

---

## 6. 脚本要求：`pipeline_test/e2e_ref_ctx_get_and_remark_analy.py`

该脚本作为“可手动跑的 E2E”，建议提供 CLI 参数并默认处理“1 篇 citing paper”以控制成本：

- `paper_to_analyze`（必填）
- `--topk-citation-cand` / `--topk-author-max-h-index-cand`（默认可设为 `15/6` 或允许用户指定）
- `--max-pages` 默认 `30`（遵循 `doc/dev/e2e_ref_ctx_get.md` 的建议）
- `--out-dir`：输出目录（建议 `log/e2e_ref_ctx_get_and_remark_analy_run`）
- `--paper-id`（可选）：仅对指定 citing paper 的 `{paper_id}.json` 打分；未指定则选择“第一个 contexts 非空的论文”
- `--dry-run`：不调用 LLM，生成伪分数以验证流程

流程建议：

1) 调用 `pcra.pipelines.run_e2e_ref_ctx_get(...)` 产出 Phase 1 JSON；  
2) 选定 1 篇（或指定的）`paper_ref_contexts/{paper_id}.json`；  
3) 对其 `ref_ctx.contexts[]` 逐条调用 LLM 打分并写出 scored JSON；  
4) 生成该论文报告；（可选）对本次 run 的所有 scored papers 生成总体报告。  

---

## 7. 报告设计（逐论文 + 总体）

### 7.1 逐论文报告（`reports/paper/{paper_id}.md`）

建议包含：

- citing paper 元信息（title/year/cited_by/max_author_h_index）
- 引用上下文条数、打分成功数、失败数
- 统计：均值/中位数/分段计数（0-3、4-6、7-10）
- Top-N 片段：
  - 最高分 3 条（附 `remark_score/reason/context` 截断）
  - 最低分 3 条（同上）

### 7.2 总体报告（`reports/summary.*`）

建议包含：

- 总 contexts 数、成功打分数、失败数
- 整体均值/分布
- 按 citing paper 聚合的均值与分布表（按均值排序）

---

## 8. 验收与回归建议

### 8.1 最小验收（本需求必须满足）

- 对 `log/e2e_ref_ctx_get_run/paper_ref_contexts/` 任意 1 个 `{paper_id}.json`：
  - 能对 `ref_ctx.contexts[]` 每条写出 `remark_score/reason`（失败需有可追踪 error）
  - 生成该 paper 的 Markdown 报告
- 对目录内多篇论文：
  - 能生成总体报告（含聚合统计与失败计数）

### 8.2 回归建议（不阻塞但推荐）

- dry-run 模式下不调用 LLM 也能跑通全流程（用于 CI/本地快速验证）
- 断点续跑：重复执行时已打分条目不会重复调用 LLM

---

## 9. 里程碑拆分（建议按 4 步交付）

### Milestone 1：上下文级打分（核心闭环）

- `pcra/remark_analy/scorer.py`：单条 context → `remark_score/reason`
- `pcra/remark_analy/batch.py`：单 paper JSON → scored JSON（支持跳过已打分）

验收：对 `W4402715937.json` 产出 scored JSON。

### Milestone 2：逐论文报告

- `pcra/remark_analy/report.py`：生成 `reports/paper/{paper_id}.md`

验收：报告包含统计与 Top-N 片段。

### Milestone 3：总体报告（聚合）

- 扫描 `{out_dir}/paper_ref_contexts_scored/*.json` 聚合统计
- 输出 `reports/summary.md` + `reports/summary.json`

验收：总体报告可读、可用于对比不同 run。

### Milestone 4：端到端脚本

- `pipeline_test/e2e_ref_ctx_get_and_remark_analy.py` 串起 Phase 1 + Phase 2（默认只分析 1 篇 citing paper）

验收：一条命令跑通并落盘全部产物。

---

## 10. 风险与降级策略

- **风险：上下文语义弱/仅列举引用** → 统一打到 `4..6` 区间，并在 `reason` 标注“背景/不明确”。
- **风险：LLM 输出不可解析** → 限次重试；仍失败则写 `remark_score=5`，并记录 `error` 便于统计。
- **风险：成本与耗时不可控** → 默认只分析 1 篇 citing paper；支持 `--max-contexts` 截断与并发限速。
