# PDF 爬取缓存与命名规则优化计划

## 目标
- PDF 文件统一命名为 `{paper_id}_{原论文标题}.pdf`，减少冲突并可追溯。
- 在 `downloads/` 内落地 PDF 缓存索引，按 `paper_id` 构造 JSON 字典记录论文元数据（标题等）。
- 下载前进行 `downloads/` 命中检查，已存在则不重复下载。

## 变更范围
- 代码：`pcra/get_pdf/*`（命名与缓存逻辑）、`pcra/pipelines/*`（调用参数与命名对齐）、`smoke_test/*`（示例参数）、`pcra/get_pdf/README.md`。
- 文档：`doc/设计文档.md`（T5 PDF 获取与落盘规则补充）。

## 设计要点
- **命名规则**：`safe_filename(paper_id)` + `_` + `safe_filename(paper_title)` + `.pdf`。
- **缓存文件**：`downloads/pdf_cache.json`，结构为 `{paper_id: {paper_id, paper_title, filename, path, source_url, updated_at, ...}}`。
- **命中检查**：
  1) 读取缓存条目并验证 `path` 是否存在；
  2) 若缓存缺失但目标文件存在（基于新命名规则），直接返回并补写缓存；
  3) 仅在未命中时执行网络下载。

## 实施步骤
1. 在 `pcra/get_pdf` 中新增缓存读写与命名构造逻辑，并把命中检查前置到下载流程。
2. 调整 `search_and_download`/`fetch_pdf_from_url` API，支持 `paper_id`/`paper_title` 参与命名与缓存。
3. 更新 `pcra/pipelines/e2e_single_paper.py` 与 `pcra/pipelines/e2e_ref_ctx_get.py` 的调用与落盘命名。
4. 更新 `smoke_test/get_pdf_smoke_test.py` 与 `pcra/get_pdf/README.md` 的用法说明。
5. 同步 `doc/设计文档.md`，补充命名规则、缓存结构与命中策略。

## 风险与回滚
- 风险：已有历史文件不符合新命名规则，可能导致重复下载。
- 缓解：基于新命名规则先检查本地文件，并在下载成功后写入缓存索引。
