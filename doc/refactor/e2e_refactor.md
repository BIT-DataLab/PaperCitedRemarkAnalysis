# 《e2e 引文上下文与评价分析 Pipeline 的结构化 Workflow 与 Trace 方案设计》

## 1. Executive Summary（≤ 10 行）
- 【事实】当前脚本将 Phase‑1 引文上下文提取与 Phase‑2 LLM 评价分析串联，产物分散在 `out_dir` 下多个 JSON/MD 以及 stdout。
- 【推断】由于缺少统一的 trace_id / stage_id 与结构化字段分区，排障需要跨文件追踪与比对，成本高。
- 【推断】将 pipeline 结构化为“分阶段 + 可传递 + 可观测”的 trace 化工作流，是后续可视化、缓存与模块替换的关键前提。
- 【事实】本文档给出 As‑Is 控制流/数据流还原、核心数据分层与 To‑Be trace 方案。
- 【事实】本文档不重写代码，不讨论模型/评分策略的优劣。

## 2. 当前 Pipeline 的结构化还原（As‑Is）

### 2.1 控制流分解（Stage‑level）
- 【事实】Stage 编号（S0‑S13）用于后续表格引用。

| Stage | 责任 | 触发条件 | 主要调用（pcra 维度，确定/推断） | 隐式依赖 |
| --- | --- | --- | --- | --- |
| S0 | 【事实】解析 CLI 参数、设置 logging、调用 E2E pipeline | 【事实】执行 `pipeline_test/e2e_ref_ctx_get_and_remark_analy.py` | `pcra.pipelines.run_e2e_ref_ctx_get_and_remark_analy【确定】` | 【事实】`sys.path` 注入 repo root；【事实】stdout 输出 |
| S1 | 【事实】初始化输出路径并进入 Phase‑1 | 【事实】S0 完成参数解析 | `pcra.pipelines.run_e2e_ref_ctx_get【确定】` | 【事实】本地文件系统（`out_dir`） |
| S2 | 【事实】OpenAlex 标题匹配目标论文 | 【事实】收到 `paper_to_analyze` | `pcra.openalex.OpenAlexFacade.work_match_by_title【确定】` | 【事实】OpenAlex API 网络；【事实】`OPENALEX_MAILTO`/`OPENALEX_USER_AGENT` |
| S3 | 【事实】获取目标论文 cited‑by 列表 | 【事实】S2 产出目标 `paper_id` | `OpenAlexFacade.work_cited_by【确定】` | 【事实】OpenAlex API 网络；【事实】排序参数硬编码 |
| S4 | 【事实】补全作者 h‑index | 【事实】S3 产出 cited‑by works | `pcra.pipelines.citations.enrich_authors_with_h_index【确定】` | 【事实】OpenAlex 作者接口网络；【事实】`max_author_lookups` 截断 |
| S5 | 【事实】按 max(h‑index) 排序并截断候选，写 metrics JSON | 【事实】S4 完成 | `rank_works_by_max_author_h_index【确定】`, `_write_json【确定】` | 【事实】文件系统；【事实】时间戳 |
| S6 | 【事实】逐候选检索并下载 PDF | 【事实】S5 产出候选列表；若 `reuse_existing` 且已有 JSON 则跳过 | `pcra.get_pdf.search_and_download【确定】` | 【事实】网络（DuckDuckGo/目标站点）；【事实】Selenium + `chrome_bin`；【事实】`downloads/` 目录 |
| S7 | 【事实】提取 PDF 全文并写入 Markdown | 【事实】S6 成功返回 `pdf.path` | `pcra.get_pdf_fulltext.get_pdf_fulltext【确定】` | 【事实】本地 PDF；【事实】PyMuPDF/ MinerU 依赖；【事实】`fulltext/` 目录 |
| S8 | 【事实】抽取引用上下文并写 per‑paper JSON | 【事实】S7 输出全文；否则写入带 error 的空 ref_ctx | `pcra.get_ref_ctx.get_paper_reference_context【确定】` | 【事实】全文内容；【事实】fallback 使用 query_title |
| S9 | 【事实】选择一个 context JSON 供评分 | 【事实】S8 生成 `paper_ref_contexts/*.json` | `_select_context_file【确定】` | 【事实】`paper_ref_contexts/` 文件结构与 JSON 结构 |
| S10 | 【事实】加载 LLM 配置或进入 dry‑run | 【事实】S9 选定 context 且 `dry_run=False` | `pcra.remark_analy.load_llm_config【确定】` | 【事实】`ref_code/chat_llm/llm_model.yaml`；【事实】`PCRA_LLM_*` 环境变量；【事实】`yaml` 包 |
| S11 | 【事实】对上下文评分并写入 scored JSON | 【事实】S9 输出 context；若 scored 已存在且 `reuse_existing` 则跳过 | `pcra.remark_analy.score_paper_contexts【确定】` → `pcra.remark_analy.scorer.score_context【确定】` | 【事实】LLM API 网络；【事实】`openai` 包；【事实】文件系统 |
| S12 | 【事实】汇总已评分文件并生成报告 | 【事实】S11 完成或已有 scored JSON | `build_paper_summary【确定】`, `write_paper_report【确定】`, `write_summary_report【确定】` | 【事实】文件系统；【事实】时间戳 |
| S13 | 【事实】返回汇总并打印 stdout | 【事实】S12 完成 | 无 pcra 调用 | 【事实】stdout |

### 2.2 数据流分解（Dataflow）
- 【事实】Phase‑1 主要以内存传递为主，但会落盘 `cand_h_index_cited_by.json` 与 `paper_ref_contexts/*.json`。
- 【事实】Phase‑2 以文件为边界读取 `paper_ref_contexts_scored/*.json` 并生成报告。

| Stage | 输入数据 | 输出数据 | 传递方式 |
| --- | --- | --- | --- |
| S0 | 【事实】CLI 参数 | 【事实】args 对象 | 【事实】内存 |
| S1 | 【事实】args | 【事实】`out_dir`/子目录路径；Phase‑1 summary | 【事实】内存 + 文件（S5/S8 产物） |
| S2 | 【事实】`paper_to_analyze` | 【事实】match_info（含 `paper_id`） | 【事实】内存 |
| S3 | 【事实】目标 `paper_id` | 【事实】cited‑by works 列表 | 【事实】内存 |
| S4 | 【事实】cited‑by works | 【事实】补全 h‑index 的 works | 【事实】内存 |
| S5 | 【事实】works 列表 | 【事实】候选列表；`cand_h_index_cited_by.json` | 【事实】内存 + 文件 |
| S6 | 【事实】候选 `paper_title` + `pdf_query_suffix` | 【事实】PDF 文件路径或 error | 【事实】文件（`downloads/`） + 内存 |
| S7 | 【事实】PDF 文件 | 【事实】全文文本 + `fulltext/<paper_id>.md` | 【事实】内存 + 文件 |
| S8 | 【事实】全文文本 + 目标标题 | 【事实】`paper_ref_contexts/<paper_id>.json` | 【事实】文件 |
| S9 | 【事实】`paper_ref_contexts/` 目录 | 【事实】选定的 context JSON 路径 | 【事实】文件读取 |
| S10 | 【事实】LLM YAML/环境变量 | 【事实】LLMConfig | 【事实】内存 |
| S11 | 【事实】context JSON | 【事实】`paper_ref_contexts_scored/<paper_id>.json` | 【事实】文件 |
| S12 | 【事实】scored JSON 列表 | 【事实】`reports/summary.md` + `summary.json` + `reports/paper/*.md` | 【事实】文件 |
| S13 | 【事实】最终 summary dict | 【事实】stdout JSON | 【事实】stdout |

## 3. 核心要素分层（最重要）
- 【事实】字段路径以 dot notation 表示；`[]` 表示数组元素。
- 【推断】Core/Params/Meta 的划分以“产出可用引文评价结果”为目标路径；允许降级路径可缺失部分 Core 字段。

### 3.1 核心数据（Core Data）

| 字段 | 所属 Stage | 生命周期（产生→消费 / 是否跨阶段） | 是否必须持久化 | 是否允许丢弃 | 适合作为 cache key / trace 索引 | 类型 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `paper_to_analyze.query_title` | S0 | S0 产生 → S2/S8 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | 输入即目标定义 |
| `paper_to_analyze.matched_title` | S2 | S2 产生 → S8/S11 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | 若匹配失败则回退到 query_title |
| `paper_to_analyze.paper_id` | S2 | S2 产生 → S3 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | 缺失会导致流程直接失败 |
| `cited_by[]`（works 列表） | S3 | S3 产生 → S4/S5 消费；跨阶段：是 | 否（现状仅内存） | 是（完成排序后） | 否 | 【事实】 | 用于候选筛选 |
| `cand_h_index_cited_by[]` | S5 | S5 产生 → S6 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | 后续每篇候选循环入口 |
| `citing_paper.paper_id` | S5 | S5 产生 → S6/S7/S8/S11 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | 作为实体索引 |
| `citing_paper.paper_title` | S5 | S5 产生 → S6/S11 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | PDF 检索与 LLM prompt 关键字段 |
| `pdf.query` | S6 | S6 产生 → S6 消费；跨阶段：否 | 否 | 是（下载完成后） | 否 | 【事实】 | 由标题 + suffix 拼接 |
| `pdf.path` | S6 | S6 产生 → S7 消费；跨阶段：否 | 是 | 是（全文成功后可回收） | 否 | 【事实】 | 无 PDF 则无法进入全文提取 |
| `fulltext.text` | S7 | S7 产生 → S8 消费；跨阶段：否 | 是（写入 `fulltext/*.md`） | 是（ref_ctx 成功后可回收） | 否 | 【事实】 | 引文上下文抽取的唯一输入 |
| `ref_ctx.query_title` | S8 | S8 产生 → S11 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | 进入 LLM prompt |
| `ref_ctx.reference_entry` | S8 | S8 产生 → S11 消费；跨阶段：是 | 是 | 否 | 否 | 【事实】 | 进入 LLM prompt |
| `ref_ctx.contexts[]` | S8 | S8 产生 → S11 消费；跨阶段：是 | 是 | 否 | 是（可对数组做 hash） | 【事实】 | 评分主体 |
| `ref_ctx.contexts[].context` | S8 | S8 产生 → S11 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | LLM 评分核心输入 |
| `ref_ctx.contexts[].match_text` | S8 | S8 产生 → S11 消费；跨阶段：是 | 是 | 否 | 否 | 【事实】 | 引文 marker |
| `selected_paper_id` | S9 | S9 产生 → S11 消费；跨阶段：是 | 否（现状仅内存/stdout） | 否 | 是 | 【事实】 | 决定评分对象 |
| `remark_score` | S11 | S11 产生 → S12 消费；跨阶段：是 | 是 | 否 | 否 | 【事实】 | 评价结果本体 |
| `reason` | S11 | S11 产生 → S12 消费；跨阶段：是 | 是 | 否 | 否 | 【事实】 | 评价解释 |

### 3.2 参数（Parameters）

| 字段 | 所属 Stage | 生命周期（产生→消费 / 是否跨阶段） | 是否必须持久化 | 是否允许丢弃 | 适合作为 cache key / trace 索引 | 类型 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `topk_citation_cand` | S0→S3 | S0 产生 → S3 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | 控制 cited‑by 拉取上限 |
| `topk_author_max_h_index_cand` | S0→S5 | S0 产生 → S5 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | 控制候选截断 |
| `max_author_lookups` | S0→S4 | S0 产生 → S4 消费；跨阶段：是 | 是 | 是 | 是 | 【事实】 | 作者 h‑index 请求上限 |
| `pdf_query_suffix` | S0→S6 | S0 产生 → S6 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | PDF 搜索 query 拼接 |
| `pdf_engine` | S0→S6 | S0 产生 → S6 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | 当前仅支持 duckduckgo |
| `fulltext_method` | S0→S7 | S0 产生 → S7 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | `pymupdfllm` 等 |
| `truncate_long_pdf` | S0→S7 | S0 产生 → S7 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | 长 PDF 截断策略 |
| `max_pages` | S0→S7 | S0 产生 → S7 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | 截断页数 |
| `window` | S0→S8 | S0 产生 → S8 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | 引文上下文窗口 |
| `match_threshold` | S0→S8 | S0 产生 → S8 消费；跨阶段：是 | 是 | 否 | 是 | 【事实】 | 标题匹配阈值 |
| `citation_style` | S8 | S8 使用默认值；跨阶段：否 | 否 | 是 | 否 | 【事实】 | 当前默认 `auto`（代码内置） |
| `reuse_existing` | S0→S6/S11 | S0 产生 → S6/S11 消费；跨阶段：是 | 是 | 是 | 是 | 【事实】 | 跳过已有 JSON |
| `paper_id` | S0→S9 | S0 产生 → S9 消费；跨阶段：是 | 是 | 是 | 是 | 【事实】 | 指定仅评分某篇 |
| `max_contexts` | S0→S11 | S0 产生 → S11 消费；跨阶段：是 | 是 | 是 | 是 | 【事实】 | LLM 评分上限 |
| `dry_run` | S0→S10/S11 | S0 产生 → S10/S11 消费；跨阶段：是 | 是 | 是 | 是 | 【事实】 | 是否跳过真实 LLM |
| `llm_config_path` | S0→S10 | S0 产生 → S10 消费；跨阶段：是 | 是 | 是 | 是 | 【事实】 | LLM YAML 路径 |
| `skip_scored` | S0→S11 | S0 产生 → S11 消费；跨阶段：是 | 是 | 是 | 是 | 【事实】 | 已评分上下文是否跳过 |
| `LLMConfig.model/base_url/temperature/max_tokens/timeout_s/json_mode` | S10→S11 | S10 产生 → S11 消费；跨阶段：是 | 是（可脱敏） | 是 | 是 | 【事实】 | 来自 YAML/环境变量 |
| `LLMConfig.api_key` | S10→S11 | S10 产生 → S11 消费；跨阶段：是 | 否（不应明文持久化） | 是 | 否 | 【事实】 | 应做脱敏/摘要 |
| `OPENALEX_MAILTO` / `OPENALEX_USER_AGENT` | S2‑S4 | 环境变量 → S2‑S4 消费；跨阶段：是 | 否 | 是 | 否 | 【事实】 | OpenAlex 客户端配置 |
| `OpenAlex match top_k=3` / `threshold=0.0` | S2 | 代码常量 → S2 消费；跨阶段：否 | 否 | 是 | 否 | 【事实】 | 当前硬编码 |
| `OpenAlex cited_by sort` | S3 | 代码常量 → S3 消费；跨阶段：否 | 否 | 是 | 否 | 【事实】 | `cited_by_count:desc,publication_year:desc` |
| `get_pdf.config.*`（MAX_PAGES/timeout 等） | S6 | 代码常量 → S6 消费；跨阶段：否 | 否 | 是 | 否 | 【事实】 | DuckDuckGo 与下载配置 |
| `get_pdf_fulltext.*`（mineru_url 等） | S7 | 代码常量 → S7 消费；跨阶段：否 | 否 | 是 | 否 | 【事实】 | Fulltext 后端默认配置 |
| `report.top_n` | S12 | 默认值 → S12 消费；跨阶段：否 | 否 | 是 | 否 | 【事实】 | 报告展示 Top N |

### 3.3 元数据（Metadata）

| 字段 | 所属 Stage | 生命周期（产生→消费 / 是否跨阶段） | 是否必须持久化 | 是否允许丢弃 | 适合作为 cache key / trace 索引 | 类型 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `generated_at`（各 JSON/报告） | S5/S8/S11/S12 | 多处产生 → 仅供阅读；跨阶段：否 | 否 | 是 | 否 | 【事实】 | 时间戳 |
| `paper_to_analyze.paper_doi` | S2 | S2 产生 → 报告展示；跨阶段：是 | 否 | 是 | 否 | 【事实】 | 目标论文 DOI |
| `paper_to_analyze.match_score` | S2 | S2 产生 → metrics JSON；跨阶段：是 | 否 | 是 | 否 | 【事实】 | OpenAlex 匹配分 |
| `citing_paper.year` | S5 | S5 产生 → 报告展示；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 候选元信息 |
| `citing_paper.cited_by_count` | S5 | S5 产生 → 报告展示；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 候选元信息 |
| `citing_paper.max_author_h_index` | S5 | S5 产生 → 报告展示；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 排序指标 |
| `citing_paper.authors[]`（author_id/name/position/h_index） | S5 | S5 产生 → metrics JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 作者明细 |
| `pdf.error` | S6 | S6 产生 → S8 JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | PDF 检索失败原因 |
| `fulltext.meta.pages_used/page_count/truncated/elapsed_s` | S7 | S7 产生 → S8 JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 全文抽取指标 |
| `fulltext.error` | S7 | S7 产生 → S8 JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 全文抽取失败原因 |
| `ref_ctx.match_score` | S8 | S8 产生 → JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 标题匹配分数 |
| `ref_ctx.ref_id` | S8 | S8 产生 → JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 引用编号（若存在） |
| `ref_ctx.citation_style_detected` | S8 | S8 产生 → JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | numeric/author_year/mixed |
| `ref_ctx.author_year_key` | S8 | S8 产生 → JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | author_year key |
| `ref_ctx.debug.ref_entry_parse_method` | S8 | S8 产生 → JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 参考文献解析方式 |
| `ref_ctx.debug.num_entries` | S8 | S8 产生 → JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 参考文献条目数 |
| `ref_ctx.debug.has_numeric_ids` | S8 | S8 产生 → JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 是否检测到数字编号 |
| `ref_ctx.debug.locator_used` | S8 | S8 产生 → JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 使用的 locator 类型 |
| `ref_ctx.debug.errors` | S8 | S8 产生 → JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 解析失败原因 |
| `ref_ctx.contexts[].start/end/line/col/ref_id` | S8 | S8 产生 → JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 位置坐标 |
| `remark_error` | S11 | S11 产生 → scored JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 单条 LLM 失败原因 |
| `remark_analy.*`（prompt_version/model/base_url/scored_count/...） | S11 | S11 产生 → scored JSON；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 评分过程元信息 |
| `summary.mean_score/median_score/bucket_counts` | S12 | S12 产生 → 报告；跨阶段：是 | 是 | 是 | 否 | 【事实】 | 汇总指标 |
| `phase1_summary.*` / `scored_summary.*` | S13 | S13 产生 → stdout；跨阶段：否 | 否 | 是 | 否 | 【事实】 | 运行级别统计 |
| `outputs.*`（out_dir/contexts_dir/...） | S1/S13 | 产生 → stdout；跨阶段：否 | 否 | 是 | 否 | 【事实】 | 路径信息 |

## 4. pcra 维度的模块化与可替换性评估

- **近似纯函数**
- 【事实】`compute_max_author_h_index` / `rank_works_by_max_author_h_index`：纯计算、可单测。
- 【事实】`pcra.get_ref_ctx.get_paper_reference_context`：无 I/O，但包含日志与分支逻辑，接近纯函数。
- 【事实】`pcra.remark_analy.build_paper_summary` / `render_paper_report`：仅基于输入结构生成文本（`render_summary_report` 额外生成时间戳）。

- **强副作用函数**
- 【事实】`pcra.openalex.OpenAlexFacade.*`：外部 HTTP 依赖。
- 【事实】`pcra.get_pdf.search_and_download`：Selenium + 网络 + 文件下载。
- 【事实】`pcra.get_pdf_fulltext.get_pdf_fulltext`：读取 PDF + 依赖外部库/服务。
- 【事实】`pcra.remark_analy.scorer.score_context`：LLM 网络调用。
- 【事实】`pcra.remark_analy.score_paper_contexts` / `write_*`：读写 JSON/MD。

- **承担多重职责的函数**
- 【事实】`run_e2e_ref_ctx_get`：OpenAlex 检索、排序、PDF 下载、全文抽取、上下文抽取与文件落盘全部混合。
- 【事实】`run_e2e_ref_ctx_get_and_remark_analy`：Phase‑1 编排 + Phase‑2 评分 + 报告生成。
- 【事实】`score_paper_contexts`：读取输入 JSON、调用 LLM、写输出 JSON 并统计指标。
- 【事实】`pcra.get_pdf.search_and_download`：检索、筛选、解析 PDF URL 与下载一体化。

- **边界不清晰导致日志混乱的根因**
- 【推断】核心数据/参数/元数据混放在同一 JSON 中，且没有统一 trace_id/run_id，导致跨阶段关联困难。
- 【推断】阶段间缺少显式“产物契约”（schema/版本），同一字段在不同 JSON 中结构不一致（如 ref_ctx 的降级结构），加大排障复杂度。

## 5. 目标架构设计（To‑Be）：结构化 Workflow + Trace

### 5.1 推荐的 Stage 划分（6–10 个）

| To‑Be Stage | 职责（单行） | 最小必要数据传递 |
| --- | --- | --- |
| T1 | 【假设】RunContext 初始化（run_id、参数冻结、输出路径规划） | `paper_to_analyze` + 参数集合 |
| T2 | 【假设】目标论文解析（OpenAlex match） | `paper_id` + `matched_title` |
| T3 | 【假设】cited‑by 拉取 | `paper_id` + works 列表（最少含 paper_id/title/authors） |
| T4 | 【假设】作者指标补全 + 候选筛选 | 候选列表（paper_id/title/max_h_index） |
| T5 | 【假设】PDF 获取（搜索/下载） | `paper_id` + `pdf.path` |
| T6 | 【假设】全文抽取 | `paper_id` + `fulltext.text` |
| T7 | 【假设】引用上下文抽取 | `paper_id` + `ref_ctx.contexts[]` |
| T8 | 【假设】上下文评分 | `paper_id` + `remark_score`/`reason` |
| T9 | 【假设】汇总与报告 | per‑paper summary + overall summary |

### 5.2 Trace Log 设计（JSON Schema）
- 【假设】每条 trace 对应一次 Stage 调用（可多次重试），采用 NDJSON 按行记录。
- 【假设】`run_id` 贯穿一次 pipeline；`trace_id` 唯一标识一次 Stage 执行；`stage_id` 固定为 Stage 名称。
- 【假设】字段分区规则：`core` / `params` / `meta` 三块；元信息统一放到 `meta.*`。

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "pcra.pipeline.trace",
  "type": "object",
  "required": ["run_id", "trace_id", "stage_id", "status", "ts", "core", "params", "meta"],
  "properties": {
    "run_id": {"type": "string"},
    "trace_id": {"type": "string"},
    "stage_id": {"type": "string"},
    "parent_id": {"type": ["string", "null"]},
    "entity_id": {"type": ["string", "null"], "description": "paper_id 等实体索引"},
    "attempt": {"type": "integer", "minimum": 0},
    "status": {"type": "string", "enum": ["start", "ok", "error", "skipped"]},
    "ts": {"type": "string", "format": "date-time"},
    "duration_ms": {"type": ["number", "null"]},
    "core": {"type": "object", "additionalProperties": true},
    "params": {"type": "object", "additionalProperties": true},
    "meta": {"type": "object", "additionalProperties": true},
    "error": {
      "type": ["object", "null"],
      "properties": {
        "type": {"type": "string"},
        "message": {"type": "string"},
        "stack": {"type": "string"}
      }
    }
  }
}
```

**单个 Stage trace 示例（简化版）**
```json
{
  "run_id": "20250101T120000Z-acde",
  "trace_id": "20250101T120000Z-acde.T7.paper-XYZ.1",
  "stage_id": "ref_ctx_extract",
  "parent_id": "20250101T120000Z-acde.T6.paper-XYZ.1",
  "entity_id": "paper-XYZ",
  "attempt": 1,
  "status": "ok",
  "ts": "2025-01-01T12:00:05Z",
  "duration_ms": 742,
  "core": {
    "paper_id": "paper-XYZ",
    "target_title": "Human-in-the-loop Outlier Detection",
    "contexts_count": 4
  },
  "params": {
    "window": 512,
    "match_threshold": 0.8
  },
  "meta": {
    "input_fulltext_path": "log/.../fulltext/paper-XYZ.md",
    "output_context_path": "log/.../paper_ref_contexts/paper-XYZ.json",
    "ref_match_score": 0.92,
    "errors": []
  }
}
```

### 5.3 Trace 在可视化与调试中的使用方式
- 【假设】按 `run_id` 聚合，按 `stage_id` 分组，即可得到 Stage‑level timeline。
- 【假设】对比 `core` 的输入/输出摘要（如 contexts_count、remark_score 分布）可快速定位异常 Stage。
- 【假设】当 `status=error` 时，通过 `parent_id` 回溯上游 Stage 输入，减少跨文件排查。

## 6. 渐进式改造计划（不写代码，但要可执行）

### 6.1 MVP 阶段（1–2 天可完成）
- 【假设】先 trace 3 个关键 Stage：S2‑S5（目标匹配 + 候选选择）、S6‑S8（PDF/全文/上下文）、S11（LLM 评分）。
- 【假设】不改业务逻辑，仅新增 trace 记录点，落盘到 `trace_log/` 并与现有 JSON 输出并存。
- 【假设】验证方式：对照 trace 中的 `paper_id`/contexts_count 与 `paper_ref_contexts/*.json` 内容一致性；对照评分计数与 `paper_ref_contexts_scored/*.json`。

### 6.2 完整版阶段
- 【假设】全 pipeline trace 化，覆盖所有 Stage + 失败/跳过分支。
- 【假设】潜在风险：trace 体积膨胀、重复记录导致 I/O 压力；LLM 参数/响应可能包含敏感信息；阶段重试会造成重复记录。
- 【假设】回归验证策略：
  - 以 dry‑run 作为基线，确认评分结果可复现；
  - 比较改造前后 `summary.json` 的统计指标一致；
  - 对关键 Stage 的 trace 采样校验（例如 contexts_count、errors 数量）。

## 7. 不确定性与验证清单（强制要求）

| 推断/假设 | 如何验证（基于现有代码/产物） | 建议新增 log / dump 点 |
| --- | --- | --- |
| 【推断】缺少统一 trace_id 是排障成本高的主要原因 | 在现有 `log/` 与 `paper_ref_contexts*/` 中尝试追溯单个 `paper_id` 的完整路径，记录所需步骤与人工比对次数 | 在每个 Stage 输出 `run_id` + `stage_id` + `entity_id` 的结构化日志 |
| 【推断】Core 数据需要包含 PDF→全文→上下文→评分链路字段，才能产出“可用评价” | 运行一次完整流程，删除/缺失其中任意一个文件（如 fulltext 或 ref_ctx）观察评分输出是否退化为空 | 在 S6/S7/S8/S11 增加 `core_missing` 标记并记录缺失字段 |
| 【假设】推荐的 To‑Be Stage 划分（T1‑T9）满足后续可视化与缓存需求 | 将当前 Stage 映射到 T1‑T9，检查是否存在“无法归类”的逻辑块或多对多依赖 | 为每个 Stage 添加 `input_schema_version` 与 `output_schema_version` |
| 【假设】Trace NDJSON + core/params/meta 分区足以支持调试与对比 | 基于一轮跑数生成 NDJSON，使用简单脚本/可视化工具聚合，检查是否能定位“评分为空/全文失败”等问题 | 在 trace 中记录 `status`/`error`/`duration_ms` 与关键计数（contexts_count, scored_count） |
| 【假设】参数脱敏（如 api_key）不会影响排障 | 人工评审 trace 中的参数字段，确认仍能定位配置问题 | 在 trace 中对敏感字段做 hash，并保留来源（env/YAML） |

