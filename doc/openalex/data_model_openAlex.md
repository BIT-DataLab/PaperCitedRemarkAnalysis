

## 1) OpenAlex 的数据模型：异构有向图（heterogeneous directed graph）

OpenAlex 把全球学术生态抽象成多个**实体（entity）**，实体之间用**关系（edges）**连接起来：论文（Work）连接作者（Author）、机构（Institution）、期刊/会议/仓库（Source）、主题（Topic）、出版商（Publisher）、资助方（Funder）等，形成一个大图谱。([OpenAlex Documentation][1])

你可以把它理解成这些核心“节点 + 边”：

* **Work（论文/书/数据集/学位论文…）**

  * 边：`Work -> referenced_works (被它引用的 Works)`；以及 `Work <- cited_by (引用它的 Works)`（通过计数/查询得到）
  * 边：`Work -> Authorships -> Author`，并挂接作者的 `Institution` 信息
  * 边：`Work -> Source / Publisher / Topics / Keywords / Funders …`（不同字段体现）
* **Author（作者）**：与 Works 通过 authorships 关联；作者对象还提供其“发表活动统计”等（见后面作者对象）。
* **Institution（机构）**：与作者/论文通过 authorships 关联，带 ROR 等外部标识。
* **Source（期刊/会议/预印本仓库等承载载体）**：Works 的主要发表来源。
* **Topic（主题）/ Keyword（关键词）**：OpenAlex 的自动标注体系（Topic 约 4500 个，Keyword 2.6 万+）。([OpenAlex Documentation][2])
* **Concept（概念）**：旧体系，官方明确 **逐步弃用，推荐改用 Topics**。([OpenAlex Documentation][3])
* **Publisher（出版商）**、**Funder（资助方）**：分别描述出版与资助组织，并与 Works 形成关联。([OpenAlex Documentation][4])

---

## 2) API 的“通用能力”：所有实体都遵循同一套玩法

OpenAlex API 是无鉴权的 REST API（免费），但有速率/日配额限制。([OpenAlex Documentation][5])
所有实体端点基本都支持这些“通用操作”：

### A. 取单个实体 / 取列表

* 单个：`GET /works/{id}`、`/authors/{id}`、`/institutions/{id}` …
* 列表：`GET /works`、`/authors`、`/topics` … ([OpenAlex Documentation][6])

### B. 搜索（search=）

对列表端点加 `search=` 做文本搜索；不同实体搜索的字段范围不同（例如 works 会在标题、摘要、可用全文等字段里做匹配）。([OpenAlex Documentation][7])

### C. 过滤（filter=）

用统一的 `filter=字段:值` 语法做结构化检索（可 AND/OR/比较运算等）。([OpenAlex Documentation][8])

### D. 排序（sort=）

如按引用数排序：`sort=cited_by_count:desc`（不同实体可用字段不同）。([OpenAlex Documentation][9])

### E. 字段裁剪（select=）

用 `select=` 只返回你需要的字段，显著降低带宽与解析成本。([OpenAlex Documentation][10])

### F. 聚合分组（group_by=）

在服务端做分桶统计（类似 facet / group by），例如按年份统计论文数、按 topic 统计规模等。([OpenAlex Documentation][11])

### G. 翻页（page / cursor）

* 小规模：`page=` + `per-page=`
* 大规模强烈推荐：`cursor=*` 开始 cursor paging，随后用返回的 cursor 翻页，可“无限翻”。([OpenAlex Documentation][12])

### H. 抽样（sample / seed）

用 `sample=N`（最多 1 万）随机抽样；`seed=` 让结果可复现。([OpenAlex Documentation][13])

### I. 速率限制 & “Polite Pool”

* 文档写明有**每秒上限与每日上限**（例如 10 req/s、100k/day），超限返回 429。([OpenAlex Documentation][14])
* 官方建议在请求中加 `mailto=you@example.com` 来进入更友好的“polite pool”（并获得更高、更稳定的速率体验，面向生产强烈建议）。([OpenAlex Documentation][10])

---

## 3) 核心实体与“能查到的信息”总览（按你最常用的）

下面按实体给你一个“字段族谱式”理解（不把每个字段逐个穷举到最末梢，但把你做系统时最关键的类别都覆盖到）。

### 3.1 Works（论文等）

Works 是你做引文/作者画像/主题分析的主入口。([OpenAlex Documentation][15])

**你通常能从 Work 里拿到：**

* **基础元数据**：标题（display_name / title）、年份（publication_year）、类型（article/book/dataset…）、语言等
* **外部 ID 集合（ids）**：如 DOI（以及 OpenAlex 自己的 ID）等（具体有哪些取决于该 work 是否能对齐外部库）
* **作者与机构（authorships）**：每个作者条目里包含作者对象的“脱水版（dehydrated）引用”和机构信息（也通常是脱水版），并说明署名顺序/角色等（字段结构见 Work/Author 对象页）。([OpenAlex Documentation][16])
* **引文关系**

  * `referenced_works`：它引用了哪些 works（通常是 OpenAlex work IDs 列表）
  * `cited_by_count`：被引用次数
  * 以及常见会有 `cited_by_api_url`（给你一个查询“哪些 work 引用了它”的入口 URL）；这通常意味着：**要拿到 citing works 列表，需要再发一次 works 查询**（这是大家做 snowball 时最常用的模式）。([Google Groups][17])
* **主题/关键词体系**：`primary_topic` 和 `topics`（以及 Keywords 体系，取决于具体 work 字段返回）([OpenAlex Documentation][2])
* **开放获取（Open Access）相关**：是否 OA、OA 类型、license、是否有可用的开放版本等（用于“只分析可下载全文”的工作流特别关键）。([OpenAlex Documentation][10])
* **摘要**：OpenAlex 出于法律原因通常不直接给 plaintext abstract，而是给 `abstract_inverted_index`（倒排索引形式，需要你自己还原）。([OpenAlex Documentation][16])
* **全文可用性**：官方说明 works 搜索会在标题/摘要/“可用全文”里检索，并且“全文搜索只覆盖子集”，你可以用 `has_fulltext` 等字段辅助判断。([OpenAlex Documentation][18])

> 实战提示：你做“引用语境分析”（找 citing papers + 抽取 cite context）时，OpenAlex 负责**元数据与引用关系图谱**；而“引用上下文”仍需要你走 PDF 获取 + 本地解析（你之前的 PyMuPDF 方案）这条链路。

---

### 3.2 Authors（作者）

作者对象会给你：作者名字、外部标识（如 ORCID，若有）、以及其作品量/被引量等聚合指标；并提供作者“在论文里声明过的机构 affiliations（含年份范围）”。([OpenAlex Documentation][19])

你关心“作者所属机构信息”时：

* 主要看 Author 对象里的 **`affiliations`**（基于作者在作品中的署名机构信息汇总而来，按年份给出）。([OpenAlex Documentation][19])
* 更细粒度（某篇论文上作者属于哪个机构）则看 **Work.authorships[].institutions**（按论文维度最准确）。

---

### 3.3 Institutions（机构）

机构对象通常包含：名称、国家/地区代码、外部标识（尤其 ROR）、以及与 works/作者相关的统计（例如 works_count/cited_by_count 等）。([OpenAlex Documentation][20])

---

### 3.4 Sources（期刊/会议/仓库）

Source 描述“承载作品的 venue”，包含名称、简称/别名、ISSN 等外部标识（若有），以及按年份的 works_count/cited_by_count 之类的时间序列统计等字段。([OpenAlex Documentation][21])

---

### 3.5 Topics / Keywords（主题与关键词）

* Topics：OpenAlex 当前主推的主题体系（约 4500），Works 上有 primary_topic 与 topics 列表。([OpenAlex Documentation][2])
* Keywords：基于 Topics 的关键词体系（2.6 万+），用于更细粒度的标签。([OpenAlex][22])

如果你做“领域聚类/统计报表”，`group_by=topics.id` 这类接口非常省事。([OpenAlex Documentation][10])

---

### 3.6 Concepts（旧概念体系：不建议新项目依赖）

官方文档明确：Concepts 在被 Topics 替代，**仍提供但不再积极维护与支持**。([OpenAlex Documentation][3])
如果你是新系统（尤其要长期维护），建议把“概念/主题”统一转向 Topics/Keywords。

---

### 3.7 Publishers / Funders

* Publisher：出版商实体（名称、别名、层级关系、国家代码、统计等）。([OpenAlex Documentation][23])
* Funder：资助方实体（别名、统计等；数据来源包含 Crossref 等）。([OpenAlex Documentation][24])

---

## 4) 你最常用的“查询范式”（直接映射到工程模块）

### 范式 1：标题 → work 匹配 → DOI/OpenAlexID

* `GET /works?search={title}` 或更严格用 filter/doi 批量方式（官方也给了 batch 的例子）。([OpenAlex Documentation][18])

### 范式 2：给定 work → 找它引用了哪些（backward citations）

* 取单个 work，看 `referenced_works` 列表；必要时再批量查 works 详情（你可用 `filter=doi:...|...` 这种方式减少请求数）。([OpenAlex Documentation][10])

### 范式 3：给定 work → 找哪些 work 引用了它（forward citations / cited by）

* 用 `cited_by_count` 知道规模
* 再用 works 查询（常见是跟随 `cited_by_api_url` 提供的入口）去拉 citing works 列表。([Google Groups][17])

### 范式 4：统计/报表（按年、按 topic、按机构…）

* `group_by=publication_year`、`group_by=topics.id`、`group_by=authorships.institutions.id` 等。([OpenAlex Documentation][10])

---

## 5) 你做系统时要提前知道的“坑/限制”（避免走弯路）

* **“引用上下文（cite context）”不在 OpenAlex 里**：OpenAlex 给你“谁引谁 + 元数据”，但不会给 PDF 中的具体引用句子；那部分仍要你抓 PDF + 本地解析（你之前的 PyMuPDF/正则方案）。
* **摘要通常不是明文**：会是 `abstract_inverted_index`，你要自己还原。([OpenAlex Documentation][16])
* **全文搜索只覆盖子集**：works 的 search 会用到“可用全文”，但并非所有 work 都有 fulltext；需要用 `has_fulltext` 等字段做策略分支。([OpenAlex Documentation][18])
* **Concepts 弃用**：新项目别把它当主分类体系。([OpenAlex Documentation][3])
* **大规模抓取要用 cursor paging + select + mailto**：这是性能和稳定性的关键组合。([OpenAlex Documentation][12])

---

如果你愿意，我可以按你正在做的 **PaperCitedRemarkAnalysis** 目标，把上面能力“落到模块级 API 设计”上：

* Work 匹配（title→work）
* cited-by 拉取（含批量优化策略：select、cursor、doi batch、请求拆分）
* 作者/机构画像提取（authorships vs author.affiliations 的取舍）
* 以及你之前问过的 **“一次检索里能不能拿到 cited-by 论文作者的 h-index”**这类信息在 OpenAlex 里该怎么建模（通常需要额外数据源/二次请求）。

[1]: https://docs.openalex.org/?utm_source=chatgpt.com "OpenAlex technical documentation: Overview"
[2]: https://docs.openalex.org/api-entities/topics?utm_source=chatgpt.com "Topics | OpenAlex technical documentation"
[3]: https://docs.openalex.org/api-entities/concepts/concept-object?utm_source=chatgpt.com "Concept object"
[4]: https://docs.openalex.org/api-entities/publishers?utm_source=chatgpt.com "Publishers"
[5]: https://docs.openalex.org/how-to-use-the-api/api-overview?utm_source=chatgpt.com "API Overview"
[6]: https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities?utm_source=chatgpt.com "Get lists of entities"
[7]: https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/search-entities?utm_source=chatgpt.com "Search entities"
[8]: https://docs.openalex.org/api-entities/works/filter-works?utm_source=chatgpt.com "Filter works"
[9]: https://docs.openalex.org/api-entities/topics/get-lists-of-topics?utm_source=chatgpt.com "Get lists of topics"
[10]: https://docs.openalex.org/api-guide-for-llms?utm_source=chatgpt.com "API Guide for LLMs"
[11]: https://docs.openalex.org/how-to-use-the-api/get-groups-of-entities?utm_source=chatgpt.com "Get groups of entities"
[12]: https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/paging?utm_source=chatgpt.com "Paging"
[13]: https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/sample-entity-lists?utm_source=chatgpt.com "Sample entity lists"
[14]: https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication?utm_source=chatgpt.com "Rate limits and authentication"
[15]: https://docs.openalex.org/api-entities/works?utm_source=chatgpt.com "Works | OpenAlex technical documentation"
[16]: https://docs.openalex.org/api-entities/works/work-object?utm_source=chatgpt.com "Work object"
[17]: https://groups.google.com/g/openalex-community/c/wvNWe8zR96s?utm_source=chatgpt.com "Expand `cited_by_api_url` to the actual list of work ids ..."
[18]: https://docs.openalex.org/api-entities/works/search-works?utm_source=chatgpt.com "Search works"
[19]: https://docs.openalex.org/api-entities/authors/author-object?utm_source=chatgpt.com "Author object"
[20]: https://docs.openalex.org/api-entities/institutions/institution-object?utm_source=chatgpt.com "Institution object"
[21]: https://docs.openalex.org/api-entities/sources/source-object?utm_source=chatgpt.com "Source object"
[22]: https://help.openalex.org/hc/en-us/articles/24736201130391-Keywords?utm_source=chatgpt.com "Keywords"
[23]: https://docs.openalex.org/api-entities/publishers/publisher-object?utm_source=chatgpt.com "Publisher object"
[24]: https://docs.openalex.org/api-entities/funders?utm_source=chatgpt.com "Funders | OpenAlex technical documentation"
