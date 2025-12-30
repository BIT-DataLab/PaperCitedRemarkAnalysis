# 引文 ctx 识别模块扩展方案（pcra/get_ref_ctx）

## 0. 背景与现状

当前 `pcra/get_ref_ctx` 的能力边界（见 `pcra/get_ref_ctx/README.md` 与 `doc/dev/模块化引用上下文识别功能.md`）：

- 仅支持在 References/Bibliography 中解析形如 `[n]` 的数字引用条目；
- 正文仅支持数字 bracket 引用：`[n]` / `[n1, n2]` / `[n1–n2]`；
- 通过「目标论文 title」在 References 中匹配到 `ref_id`，再在正文中找 `ref_id` 的引用位置并截取上下文。

`doc/dev/引用上下文识别功能拓展需求.md` 提出新的引用形态：author-year（作者-年份）+ 年份后缀字母，如 `(Wu et al. 2021a)`，当前模块无法完成：

1) References 条目往往不含 `[n]` 数字编号；  
2) 正文引用不再是 `[n]`，而是 `(第一作者姓氏 ... 年份编号+字母序)`。

本方案目标是在不破坏现有数字引用能力的前提下，扩展 author-year 引用识别，并补齐一些必要的鲁棒性能力。

---

## 1. 需求解读（来自 `doc/dev/引用上下文识别功能拓展需求.md`）

### 1.1 样例 References（无 `[n]`）

- `Whalen, D. 2016. ...`
- `Wu, M.; ... 2021a. ...`
- `Yang, K.; ... 2023. ...`
- `Zhang, S.; ... 2019. ...`

### 1.2 样例正文引用

- 单个：`TACTICZERO (Wu et al. 2021a)`
- 多个：`... (Bansal et al. 2019a; Kaliszyk, Chollet, and Szegedy 2017), ...`
- 说明：`2021a` 的 `a/b/c...` 用于区分同一作者同一年多篇文献在引用列表中的序号。

### 1.3 隐含约束

- 需要把「引用文本」与「References 中的某一条目」建立可追溯的映射；
- 仍然以 “给定被引论文 title” 为入口（E2E 管线依赖该入口），并输出若干正文上下文片段。

---

## 2. 设计目标

### 2.1 功能目标

- 支持 author-year 引用：识别 `(Surname ... 2021a)` / `Surname et al. (2021a)` 等变体。
- 支持同一括号内多引用：分号/逗号分隔时能定位到目标引用项，并返回该括号对应的上下文。
- References 无数字编号时，仍能解析出参考文献条目并完成 title 匹配。

### 2.2 兼容性目标

- 现有 API `pcra.get_ref_ctx.get_paper_reference_context(md_text, title, window, match_threshold)` 保持可用；
- 对数字引用格式的行为不回退；
- E2E 管线 `pcra/pipelines/e2e_ref_ctx_get.py` 不需要修改或仅需极小修改（推荐：尽量不改）。

### 2.3 鲁棒性目标（本方案建议新增）

- 面对 PDF 抽全文的噪声（断行、连字符、异常空白、标点漂移）仍尽可能稳定；
- 输出中提供足够的 debug 信息（命中方式、匹配 key、失败原因），便于定位问题；

---

## 3. 总体方案（不改入口，扩展内部“定位器”）

把“如何在正文中定位某条 References 条目”抽象为 `locator`（引用定位器）：

- Numeric 模式：`locator = ref_id:int`（现有方案）
- Author-year 模式：`locator = (first_author_surname, year_with_suffix)`（新增）

整体流程保持一致：

1. `split_body_and_references`：拆分正文与 References（可顺带增强 heading 识别，见 §7.1）。
2. `parse_reference_entries`：将 References 拆为条目列表（新增对无编号条目分段）。
3. `find_reference_entry_by_title`：按 title 匹配到目标条目（沿用现有模糊匹配）。
4. `build_locator(match.entry)`：
   - 若条目能解析数字 `ref_id` → 使用 numeric locator；
   - 否则从条目中提取 author-year key → 使用 author-year locator；
5. `extract_citation_contexts(body, locator)`：在正文中查找引用出现位置，截取上下文。

---

## 4. 模块级扩展点（建议落到 `pcra/get_ref_ctx`）

### 4.1 `references.py`：References 条目分段扩展（核心）

现状：只靠 `^\s*\[(\d+)\]` / `- [n]` 这类 start marker 分段，无法覆盖无编号 References。

扩展方案：在 `parse_reference_entries` 中加入一个“无编号 fallback 分段器”：

1) 若检测到数字编号 marker（现有）→ 走原逻辑；  
2) 否则尝试以下策略（从强到弱，命中一种即可）：

- **策略 A：按空行分段**  
  - 以连续空行（`^\s*$`）作为段落边界；
  - 段落长度过短（如 < 20 chars）则合并到下一段；
  - 为每段赋予**合成 ref_id**（例如从 1 开始递增）。
- **策略 B：按“年份锚点行”分段**  
  - 使用年份模式 `\b(19|20)\d{2}[a-z]?\b`；  
  - 在 References 文本中查找“疑似条目起始行”：通常为 `^<Surname>, ... <Year>`；
  - 以这些起始行作为 start marker 分段。
- **策略 C：按 bullet/编号分段（非 `[n]`）**  
  - 支持 `- ` / `* ` / `• ` / `1.` / `1)` 等列表起始；
  - 结合年份锚点过滤（避免把正文残片误切进 References）。

输出数据结构建议增强（兼容优先，字段可先内用后外放）：

- `ReferenceEntry(ref_id: int, raw_text: str, first_author: str|None, year: str|None, year_suffix: str|None, author_year_key: str|None)`

其中 `ref_id`：

- 有真实 `[n]` 时使用真实 n；
- 无真实 n 时使用合成 id（保证 smoke_test 与 E2E 仍能基于 truthy `ref_id` 判定“匹配成功”）。

### 4.2 `match.py`：title 匹配保持不变，增加“可解释性输出”

保留现有基于 token recall + SequenceMatcher 的标题匹配逻辑；建议补充：

- 返回“命中的条目切片”（例如 title_norm 是否包含于 entry_norm）；
- 便于后续调参：`match_threshold` 不同文献库/抽全文方法下最佳值可能不同。

（实现层面：可在 `ReferenceMatch` 中加 `reason` 字段或在 facade 输出 debug 字段。）

### 4.3 `citations.py`：新增 author-year 引用解析与匹配

新增 `extract_author_year_citation_contexts(body_text, target_key, window)`，并在 facade 中与 numeric 结果合并。

建议采用“两阶段”的稳健方案：

**阶段 1：候选 citation span 检出（尽量高召回）**

- Parenthetical cluster：匹配 `(...)`，并要求括号内出现年份锚点（降低误报）  
  - 例：`(Wu et al. 2021a; Kaliszyk ... 2017)`
- Narrative year-in-parens：匹配 `Surname ... (2021a)`  
  - 例：`Wu et al. (2021a)`

**阶段 2：span 内部解析 + 目标匹配（提高精度）**

- 将括号内部按 `;` 分割为 citation items；
- 对每个 item 提取：
  - `first_author_surname`：item 中第一个大写开头的 token，或逗号前 token（如 `Kaliszyk,` → `Kaliszyk`）
  - `year_with_suffix`：`(19|20)\d{2}[a-z]?`
- 仅当 `(surname == target_surname) AND (year_with_suffix == target_year_with_suffix)` 命中时，认为该 span 引用了目标条目。

**可选增强（提升真实数据覆盖）**

- 允许可选逗号：`Wu et al., 2021a`
- 支持 `and/&` 双作者：`Kaliszyk and Urban 2015`
- 支持同一作者同年多篇合写：`2021a,b`（可解析成两个 key）

上下文截取与现有一致：对命中的 `span`（括号整体或“作者-年份片段”）取 `window` 字符前后。

### 4.4 `facade.py`：风格自动选择 + 输出扩展（保持兼容）

建议新增可选参数（默认 `auto`）：

- `citation_style: Literal["auto","numeric","author_year"] = "auto"`

行为：

- `numeric`：保持当前逻辑；
- `author_year`：要求从 reference entry 中解析到 author-year key，否则返回空 contexts 并输出 error/debug；
- `auto`：若 entry 有数字 `ref_id` 就跑 numeric；若能解析 author-year key 就跑 author-year；两者都可得时合并去重。

输出保持现有字段，并建议新增（不影响旧调用方）：

- `citation_style_detected`: `"numeric"|"author_year"|"mixed"|None`
- `author_year_key`: 例如 `"Wu|2021a"`（或结构化字段）
- `debug`: { `ref_entry_parse_method`, `num_entries`, `locator_used`, `errors`... }

这样即使不修改 E2E 管线，也能在 JSON 里看到为什么某篇没有命中（是 References 分段失败、title 匹配失败、key 提取失败、还是正文没出现该 key）。

---

## 5. 鲁棒性增强建议（超出需求但性价比高）

### 5.1 文本噪声处理（不改变索引或可回映射）

问题：PDF 抽全文常见断行/连字符导致 `Wu et al. 2021a` 被切成 `Wu et al.\n2021a` 或 `W-\nu`。

建议策略：

- **匹配用“宽松正则”优先**：在关键空白处允许 `\s+`（包含换行）。
- 若必须做 normalization（如去掉连字符断行），需提供 index 映射；否则 start/end/line/col 会不可靠。
  - 方案 A：仅在“候选 span 内”做局部 normalization，再用原文定位 span 边界；
  - 方案 B：构建 `search_text` 与 `orig_text` 的位置映射表（实现复杂，建议后置）。

### 5.2 去重与冲突处理

- 合并 numeric 与 author-year 结果时，按 `(start,end,match_text)` 去重；
- 同一 span 内可能命中多个规则时，保留“更具体”的匹配（如 author-year item 命中优先于仅年份锚点）。

### 5.3 References 标题识别扩展（可选）

当前仅支持英文 `References|Bibliography` 单行标题；建议加入（可配置开关）：

- `Reference(s)` / `REFERENCES` / `References and Notes`
- 中文 `参考文献`

并保持“取最后一个 heading 作为 References 起点”的策略不变。

---

## 6. 测试与验收（建议新增 smoke + 回归）

### 6.1 Author-year 样例 smoke test

新增一个最小样例 Markdown（推荐放 `smoke_test/fixtures/author_year_sample.md`）包含：

- References：使用需求文档中的 4 条参考文献（含 `2021a`/`2019a`）
- Body：包含 `(Wu et al. 2021a)` 与 `(Bansal et al. 2019a; ...)`

新增 smoke 脚本（例如 `smoke_test/get_ref_ctx_author_year_smoke_test.py`）：

- 输入该 fixture，title 选择 `TacticZero: Learning to Prove Theorems from Scratch with Deep Reinforcement Learning`
- 断言：
  - 能匹配到 reference_entry（`ref_id` truthy）
  - `author_year_key == Wu|2021a`
  - contexts 至少包含 1 条，且 match_text 包含 `Wu` 与 `2021a`

### 6.2 数字引用回归

保留现有 `smoke_test/get_ref_ctx_smoke_test.py` 行为，通过 `downloads/HippoRAG_fulltext.md` 回归验证：

- `ref_id` 仍为真实数字；
- contexts 数量/大致位置不明显变化（允许小幅变化但不应为 0）。

---

## 7. 里程碑拆分（可审阅后再排期）

### Phase 1：References 分段与 key 抽取（先让 title 匹配成功）

1. 在 `references.py` 增加无编号分段 fallback（§4.1），并为条目生成合成 `ref_id`。  
2. 在 `ReferenceEntry` 中增加 `first_author`/`year_with_suffix` 抽取函数（允许失败）。  
3. facade 输出 `debug.ref_entry_parse_method` 与 `num_entries`。

验收：对需求样例 References，`find_reference_entry_by_title` 能找到目标条目。

### Phase 2：Author-year citation 检出与上下文截取

1. 在 `citations.py` 新增 author-year 的 span 检出与 item 解析（§4.3）。  
2. facade 增加 `citation_style="auto"` 并合并去重（§4.4）。  

验收：对需求样例正文，能提取到包含 `(Wu et al. 2021a)` 的上下文。

### Phase 3：鲁棒性与可观测性增强（可选）

1. 支持更多变体：`Wu et al., 2021a`、`Wu et al. (2021a)`、`2021a,b`。  
2. References heading 识别扩展（§5.3）。  
3. 输出 debug 指标与失败原因分类，便于 E2E 大规模跑时统计。

---

## 8. 风险与回退策略

- **风险：References 无明显分段/空行** → fallback 到“年份锚点行 start marker”；仍失败则返回 `error="reference entries not found"` 并保留原行为（不崩溃）。  
- **风险：正文年份与姓氏误匹配** → 两阶段策略 + 仅在括号/叙述引用结构中判定，降低误报；必要时增加白名单规则（如必须出现 `et al.` 或 `and/&`）。  
- **回退：key 抽取失败** → 只要 numeric 可用就走 numeric；都不可用则明确在 `debug/errors` 中说明原因，避免 silent failure。
