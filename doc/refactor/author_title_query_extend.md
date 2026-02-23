T6 Fellow 校验扩展落地方案（DuckDuckGo + Selenium + 本地 LLM）
摘要
将 lookup.py 从“仅 OpenRouter 联网搜索”扩展为“可配置双模式”，并按你的选择默认 local_only。
新增本地链路：DuckDuckGo 检索 -> 学者主页静态正文抽取 -> 失败时 Selenium 动态渲染抽取 -> 本地 LLM 判定 Fellow。
保持现有 pipeline 主接口和结果结构不变：仍返回 statuses(dict) + sources(list) + error(optional)，兼容 T4b 逻辑。
保留 OpenRouter 流程用于 openrouter_only 或 local_with_fallback 模式。
公开接口/配置/类型变更
lookup.py 的 lookup_fellow_status(...) 函数签名保持不变。
llm_model_template.yaml 新增 fellow_lookup 配置段：
mode: local_only | local_with_fallback | openrouter_only（默认 local_only）
allow_wikipedia: true（默认开启，且主页优先）
max_results: 3（被 fellow_web_search_topk 覆盖）
profile_char_limit: 8000（按你的要求）
min_profile_chars: 200
fellow_web_search_topk 语义调整为“每位作者最多处理的候选主页数量”，参数名保持不变，避免破坏 CLI/调用方。
fellow_lookup.json 缓存版本从 1 升级为 2，避免旧 key 误命中新逻辑结果。
详细实现（文件级）
lookup.py
保留并封装现有 OpenRouter 逻辑为 _lookup_via_openrouter(...)。
新增本地配置读取 _read_fellow_lookup_settings(...)，并实现模式分发：
local_only: 只跑本地链路。
local_with_fallback: 本地链路全 Unknown 或技术失败时回退 OpenRouter。
openrouter_only: 保持旧行为。
新增本地链路函数 _lookup_via_local_web_and_llm(...)，流程固定为两阶段：
Phase 1 静态抓取：search_duckduckgo 检索候选 URL，requests 拉静态 HTML，trafilatura.extract(output_format="html") 抽正文，markdownify 转 Markdown，截断到 profile_char_limit。
Phase 2 动态抓取：当 Phase 1 无有效 bio 时，用 Selenium 打开候选页取 page_source，重复正文抽取与 Markdown 转换。
新增 URL 过滤/排序逻辑：
只允许“个人主页/院系 profile 页面”与 Wikipedia（主页优先）。
明确过滤 aaai.org 等组织站点及明显非个人简介页。
新增本地 LLM 判定 _call_local_text_llm_for_honor_check(...)：
使用 text 段配置（OpenAI 兼容接口，复用当前本地 Ollama 调用方式）。
输出强约束 JSON：is_target_scholar、has_valid_profile_content、三个组织的 status/year。
仅基于页面文本证据判定；无证据必须 Unknown。
新增状态合并策略：
初始全 Unknown。
Yes 优先级最高并锁定对应来源。
No 只在明确证据时保留，否则保持 Unknown。
sources 输出实际用于判定的页面 URL（去重）。
新增缓存 key 维度：加入 mode、profile_char_limit、allow_wikipedia、本地模型名，避免跨模式污染。
e2e_single_paper_citation_analysis.py
更新 --fellow-web-search-topk help 文案为“候选主页处理上限”，不改参数名与默认值。
llm_model_template.yaml
增加 fellow_lookup 新段并给出三种模式示例。
保留 openrouter_web_search，但标注“仅 fallback 或 openrouter_only 模式需要”。
readme.md 与 readme_cn.md
更新“LLM 配置说明”：Fellow 阶段默认可不依赖 OpenRouter。
补充 fellow_lookup.mode 的含义与推荐配置。
设计文档.md
将 T4b 描述从“OpenRouter Web Search”改为“本地检索链路 + 可选 OpenRouter 回退”。
更新成本控制条目：静态优先、动态 fallback、候选数上限、字符截断上限。
requirements.txt
增补并固定依赖：trafilatura==2.0.0、markdownify==1.2.2、beautifulsoup4==4.14.3。
判定逻辑（最终规则）
仅在“目标学者匹配 + 页面正文有效”时采纳该页面结果。
页面无 bio 或正文过短时不直接判定，进入动态渲染重试。
仍无有效信息时该页面记为无效，不作为证据。
作者最终状态按多页面合并得到；若无有效证据则三项均 Unknown，error=None（这是业务降级，不是技术错误）。
异常处理策略
技术异常（依赖缺失、Selenium 启动失败、配置缺失、LLM 调用异常）返回 error，并保持结果安全降级为 Unknown。
local_with_fallback 下本地失败会触发 OpenRouter；若回退也失败，返回本地降级结果并附 fallback_failed:*。
网络不可达或检索无结果不视为异常中断，只产生 Unknown。
测试用例与场景
配置解析
无 fellow_lookup 时默认 local_only。
三种 mode 可正确分发。
本地链路核心逻辑
静态正文有效时不进入动态渲染。
静态无效且动态有效时可产出状态。
URL 过滤能屏蔽组织站点，仅保留主页/Wikipedia。
合并与降级
多来源冲突时 Yes 优先。
无证据时返回全 Unknown 且 error=None。
local_with_fallback 在全 Unknown 时触发 OpenRouter。
缓存
同作者不同 mode/profile_char_limit 不串缓存。
cache hit 能直接返回一致结构结果。
集成冒烟
运行 test_llm_fellow_lookup.py 验证本地模式可出结构化结果（允许 Unknown，但结构必须合法）。
验收标准
在 mode=local_only 时，即使 openrouter_web_search 未配置，也能完成 T4b 并输出合法 fellow_status。
输出字段与下游兼容：fellow_status 仍为 ieee/acm/aaai -> Yes|No|Unknown，fellow_status_sources 仍为 URL 列表。
处理成本受控：每作者最多处理 fellow_web_search_topk 个候选页，每页最多两轮抽取（静态+动态），每轮文本截断到 8000 字符。
明确假设与默认值
默认模式：local_only。
动态 fallback 技术：Selenium（不引入 Playwright）。
来源范围：主页优先 + Wikipedia 可用。
正文截断阈值：8000 字符。
对无证据场景优先返回 Unknown，不做推断式 No。