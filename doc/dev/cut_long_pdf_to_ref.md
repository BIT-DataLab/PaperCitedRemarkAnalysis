
# pdf引用解析
只用关注文档的正文和引用部分，有些论文会有很长的附录，我们不要把附录也让MinerU解析，否则会很慢。
一般论文pdf的正文部分只出现在前20个page，当pdf的page数大于20时，我们只截取前20页进行解析。

## 代码实现位置

- 核心模块：`pcra/get_pdf_fulltext`
- 截断参数：
  - `truncate_long_pdf: bool = True`
  - `max_pages: int = 20`

当 `truncate_long_pdf=True` 且 `page_count > max_pages` 时，会先生成一个仅包含前 `max_pages` 页的临时 PDF，再交给后端解析。

## Smoke Test

`python3 tools/get_pdf_fulltext_smoke_test.py <pdf_path> --method pymupdfllm --max-pages 20 --out <out.md>`
