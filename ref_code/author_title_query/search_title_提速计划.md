
请你根据下面的计划，参照现有的 @ref_code/author_title_query/llm_web_search_title_demo.py，
写一个新的 @ref_code/author_title_query/fast_llm_web_search_title_demo.py

 python ref_code/author_title_query/
     fast_llm_web_search_title_demo.py --name "Guoliang Li" --affiliation "Tsinghua
     University"

# ⚡ P0 极限提速（Cursor 快速执行版）

## 🎯 目标

在**不改整体架构、不引入新依赖**的前提下，通过 prompt 约束 + 参数调整 + 轻量缓存，
将 `llm_web_search_title_demo.py` **单学者 Stage1 延迟从 ~30s 降至 8–15s**，
并避免 Stage2 导致的隐性翻倍。

---

## 1️⃣ Stage 1 Prompt 强约束（必须修改）

在 `PROMPT_HONOR_CHECK` 末尾加入以下内容（逐条保留）：

```text
STRICT CONSTRAINTS:

1. Prefer official HTML pages.
   - Do NOT open or cite PDF files unless unavoidable.
   - Avoid CV PDFs and IEEE Xplore PDFs.

2. Evidence limit:
   - Use at most ONE reliable source per organization.
   - Stop searching once evidence is found.

3. Search budget:
   - Shallow search only.
   - If evidence is not found quickly, return "Unknown".
   - Do NOT attempt exhaustive verification for No / Unknown.

4. Output format (must follow exactly):

IEEE Fellow: Yes | No | Unknown
Year: <year or N/A>
Source: <single URL or N/A>

ACM Fellow: Yes | No | Unknown
Year: <year or N/A>
Source: <single URL or N/A>

AAAI Fellow: Yes | No | Unknown
Year: <year or N/A>
Source: <single URL or N/A>
```

---

## 2️⃣ Web Search 参数下调（必须改）

修改默认值：

```python
max_results = 2        # 原 5
timeout_s  = 25       # 原 60
max_retries = 0       # 原 2
```

原则：**宁可 Unknown，不阻塞 pipeline**。

---

## 3️⃣ Stage 2 默认关闭

将 argparse 中：

```python
default="auto"
```

改为：

```python
default="never"
```

并添加注释说明：Stage 2 是高延迟操作，仅允许显式开启。

---

## 4️⃣ 加入本地 Cache（P0 必须）

### Cache Key

```text
(name_norm, affiliation_norm, model, max_results, "stage1")
```

### Cache 内容

* raw LLM output
* parsed statuses
* citations
* timestamp

### 策略

* TTL：180 天
* Cache hit → **直接返回，不调用 OpenRouter**

实现方式：SQLite / JSON 文件均可。

---

## 5️⃣ 验收标准（自测）

* 单学者 Stage1：

  * p50 ≤ 12s
  * p95 ≤ 18s
* 同一学者二次查询：

  * ≤ 100ms（Cache 命中）
* 不出现：

  * 无必要 PDF 打开
  * 单 org >1 个 source
  * Stage 2 自动触发

---

## ❌ 不做范围

* 不引入新搜索 API
* 不做 agent / workflow 重构
* 不做离线 Fellow 知识库
* Unknown 是合法最终结果

---

📦 **交付物**

1. 修改后的脚本
2. 更新后的 `PROMPT_HONOR_CHECK`
3. Cache 实现
4. Before / After 延迟对比说明

---

如果你愿意，下一步我可以直接帮你出 **P1「你掌控搜索」的接口设计 + prompt**，无黑盒 web-search。
