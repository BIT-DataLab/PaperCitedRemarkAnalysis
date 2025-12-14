# OpenAlex 模块设计（PaperCitedRemarkAnalysis）

本设计文档用于支撑系统集成（见 `doc/模块设计.md`、`doc/需求文档.md`），提供一组**顶层接口清晰**、**内部可组合**、并且便于后续做缓存/并发/批量/分页优化的 OpenAlex 访问模块。

> 约束：重构后的模块 **仅包含 OpenAlex**，不包含 Semantic Scholar 相关接口。

---

## 1. 设计目标

1. **顶层接口稳定**：对上层系统只暴露固定的 6 个 API，覆盖论文与作者的“match / meta / list”三类能力。
2. **模块低耦合可组合**：Works/Authors/HTTP Client/相似度打分/字段集管理彼此解耦，上层 pipeline 按需组装。
3. **单次请求尽量拿全**：每个顶层接口默认通过 `select` + `per-page` 在一次请求内获取足够信息；需要更多数据再显式调用其它接口（避免隐式联动）。
4. **为优化预留插槽**：批量拉取作者指标（h-index 等）、cursor 翻页、重试/退避、缓存等都集中在可替换层实现。

---

## 2. 顶层接口（Facade）定义

统一约定：
- `paper_id` / `work_id`：OpenAlex Work short id，例如 `W2626778328`
- `author_id`：OpenAlex Author short id，例如 `A5112456378`
- OpenAlex 返回的 `id` 常为 URL（如 `https://openalex.org/W...`），模块内部会归一化为 short id，便于后续 `filter=openalex_id:...` 等批量查询。

### 2.1 根据论文题目查论文 id + 可选元数据

**接口**
- `work_match_by_title(title, *, top_k=3, threshold=0.6, fields=None) -> dict`

**网络请求（默认 1 次）**
- `GET /works?search=<title>&per-page=<top_k>&select=<WORK_MATCH_SELECT>`

**返回结构（推荐）**
```json
{
  "query": "...",
  "match": { "paper_id": "W...", "paper_title": "...", "paper_doi": "...", "year": 2023, "authors": [...] },
  "match_score": 0.82,
  "candidates": [ {..}, {..}, ... ]
}
```

### 2.2 根据论文 id 查论文元数据

**接口**
- `work_meta(paper_id, *, fields=None, decode_abstract=True) -> dict`

**网络请求（默认 1 次）**
- `GET /works/{paper_id}?select=<WORK_META_SELECT>`

**返回结构（推荐）**
```json
{
  "paper_id": "W...",
  "meta": { ...OpenAlex Work object (选取字段) ... },
  "abstract": "..."   // decode_abstract=True 时，从 abstract_inverted_index 还原
}
```

### 2.3 根据论文 id 查 cited_by 论文列表（包含 id/题目）

**接口**
- `work_cited_by(paper_id, *, top_k=20, fields=None, sort=None) -> list[dict]`

**网络请求（默认 1 次）**
- `GET /works?filter=cites:{paper_id}&per-page=<top_k>&select=<WORK_CITED_BY_SELECT>&sort=<DEFAULT>`

**返回结构（推荐）**
```json
[
  { "paper_id": "W...", "paper_title": "...", "year": 2020, "cited_by_count": 123, "authors": [...] },
  ...
]
```

> 注意：该接口**不做作者指标 enrich**（例如 h-index），只返回 citing works 自带的 `authorships` 脱水作者信息（id/name/orcid/机构）。

---

### 2.4 根据作者名查作者 id + 可选元数据

**接口**
- `author_match_by_name(name, *, top_k=3, threshold=0.6, fields=None) -> dict`

**网络请求（默认 1 次）**
- `GET /authors?search=<name>&per-page=<top_k>&select=<AUTHOR_MATCH_SELECT>`

**返回结构（推荐）**
```json
{
  "query": "...",
  "match": { "author_id": "A...", "author_name": "...", "h_index": 40, "cited_by_count": 12000, ... },
  "match_score": 0.77,
  "candidates": [ {..}, {..}, ... ]
}
```

### 2.5 根据作者 id 查作者元数据（h_index 等）

**接口**
- `author_meta(author_id, *, fields=None) -> dict`

**网络请求（默认 1 次）**
- `GET /authors/{author_id}?select=<AUTHOR_META_SELECT>`

**返回结构（推荐）**
```json
{
  "author_id": "A...",
  "meta": { ...OpenAlex Author object (选取字段) ... },
  "h_index": 40,
  "works_count": 123,
  "cited_by_count": 12000
}
```

### 2.6 根据作者 id 查作者高引用量论文列表（按引用量/时间排序）

**接口**
- `author_top_works(author_id, *, top_k=20, sort=None, only_first_author=False, fields=None) -> list[dict]`

**网络请求（默认 1 次，常用场景）**
- `GET /works?filter=authorships.author.id:{author_id}&per-page=<top_k>&sort=<DEFAULT>&select=<AUTHOR_TOP_WORKS_SELECT>`

**only_first_author 说明**
- OpenAlex Works filter 目前不支持 `authorships.author_position` 直接过滤；因此 `only_first_author=True` 需要在客户端基于 `authorships[].author_position` 做本地筛选。
- 为提高召回率，可以在实现中将 `per-page` 提升到较大值（例如 200），必要时再引入 cursor 翻页（多次请求），但这属于 pipeline 级优化，不应隐式耦合到其它接口。

---

## 3. 内部模块划分（可维护/可替换）

建议落地为 Python 包 `pcra/openalex/`，结构如下：

```
pcra/
  openalex/
    client.py      # HTTP/重试/退避/mailto/user-agent/cursor paging
    fields.py      # 每个顶层接口的默认 select / sort 字段集
    works.py       # Work 相关“资源 API”（不跨实体联动）
    authors.py     # Author 相关“资源 API”（含批量作者指标接口）
    facade.py      # 6 个顶层接口，负责“编排 + 输出归一化”
    utils.py       # id 归一化、abstract 还原等纯函数
  domain/
    scoring.py     # 名称相似度/匹配策略（纯函数）
  pipelines/
    citations.py   # 模块2：cited_by + 作者指标 enrich + h-index 规则筛选（可选）
```

模块边界原则：
- `works.py` / `authors.py`：**只做单实体请求封装**（请求参数、select、分页），不做跨实体 enrich。
- `facade.py`：对上层提供稳定 API；在必要时调用 works/authors，但不做复杂业务筛选（筛选逻辑放 pipelines）。
- `pipelines/`：系统业务组合层（对应 `doc/模块设计.md` 的模块 1/1.1/2），允许多次请求，但必须显式、可控、可替换。

---

## 4. 字段集（select）管理策略

所有顶层接口的默认 `select` 字段集中定义在 `pcra/openalex/fields.py`，便于后续统一优化：
- 增减字段不会影响调用方代码
- 便于针对不同阶段（检索/筛选/分析）维护不同字段集
- 可按需覆盖：顶层接口提供 `fields=` 参数（list 或逗号分隔字符串）

---

## 5. 性能与耦合控制（关键点）

### 5.1 禁止隐式“作者指标请求”嵌入 cited_by

`work_cited_by()` 返回 citing works 的脱水作者信息即可；需要作者学术指标时，采用 pipeline 显式 enrich：

1. `works = work_cited_by(paper_id)`
2. `author_ids = collect_authors(works)`
3. `metrics = author_metrics_bulk(author_ids)`（批量请求）
4. `attach_metrics(works, metrics)`
5. `filter_by_hindex(works, ...)`

### 5.2 批量作者指标（减少 N 次 /authors/{id}）

OpenAlex 支持：
- `GET /authors?filter=openalex_id:A1|A2|...&select=...`

因此 `authors.py` 应提供：
- `get_authors_by_openalex_ids(author_ids, *, select=AUTHOR_METRICS_SELECT, chunk_size=...)`

该策略可把“每篇 citing work 的每个作者一个请求”的 N×M 次请求，压缩为若干次批量请求。

### 5.3 大规模结果：cursor paging

当 `top_k` 很大或需要高召回（例如 `only_first_author=True` 且作者论文很多）时，采用 cursor 翻页：
- `GET /works?filter=...&cursor=*`
- 后续用 `meta.next_cursor` 继续

cursor paging 逻辑应集中在 `client.py`，由调用方（pipeline/facade）显式启用。

---

## 6. 与系统模块的对齐关系（doc/模块设计.md）

- 模块1（论文 id 检索）：
  - `work_match_by_title()`
- 模块1.1（作者论文检索）：
  - `author_match_by_name()` → `author_top_works()`
- 模块2（被引关系检索和筛选）：
  - `work_cited_by()` →（pipeline）`author_metrics_bulk()` → `filter_by_hindex()`

---

## 7. 重构落地计划（从 tools/ 迁移到 pcra/）

1. 新增 `pcra/openalex/*` 与 `pcra/domain/scoring.py`，先保证 6 个顶层接口可用（OpenAlex only）。
2. 将 `tools/paper_info_lookup.py`、`tools/author_profile_lookup.py`、`tools/cited_by_lookup.py` 改造为“薄 CLI”，内部只调用 `OpenAlexFacade`。
3. 将模块2的 h-index enrich/filter 提取到 `pcra/pipelines/citations.py`（可选，但推荐用于彻底解耦）。
4. 删除/移除 tools 中 Semantic Scholar 路径代码，避免耦合与维护成本。
