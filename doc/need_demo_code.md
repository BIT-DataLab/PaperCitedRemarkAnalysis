# 需要先写的 demo 代码清单

- 引用关系解析和引用文献元数据获取 ：根据论文名 获取引用这篇论文的论文列表, 列表中的每篇论文含 论文名、作者列表(越详细越好-所属机构、h-index信息都有就最好)，数据源： OpenAlex / Semantic Scholar

- 引用者资质信息获取：从引用文献元数据或作者主页/学术库抓取头衔、机构、H-index，并给出 Fellow/机构白名单/H-index 阈值筛选的示例代码。 (这一步有可能包含在 "引用文献元数据获取" 中)

- PDF获取爬虫： 根据论文标题，爬取论文pdf: Google Scholar 或 DuckDuckGo 等网页搜索到论文/PDF 的流程（headless 浏览器配置、翻页、反爬应对、深度链接解析--某些会议官网能找到指定名称论文的主页，然后里面有1个名字中包含Download的超链接，访问这个链接才能得到pdf--但链接名中本身不含论文名信息）

- PDF 文本抽取与引用上下文解析：PDF → 正文文本（pymupdf/pdfplumber 任意）；用正则/规则识别 `[12]`等标记并返回上下文片段。

- LLM 情感判定调用：给定 contexts 列表的最小 prompt + 调用示例，确保只返回 `positive` / `normal` / `negative` 单标签结果。
