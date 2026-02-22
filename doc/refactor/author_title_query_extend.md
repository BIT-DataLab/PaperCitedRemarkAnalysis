
# T6 TopK 作者 Fellow 校验（IEEE/ACM/AAAI） 功能扩展
- 扩展程序的逻辑，让它可以不依赖于openrouter-api (可用本地的llm-api，需要从学者主页截取包含作者头衔介绍的文本)
当前程序流程在分析单篇论文时，学者头衔校验阶段（找大佬阶段）依赖openrouter-api把学者主页检索+头衔校验一条龙解决，但这个操作依赖openrouter的搜索api,比较昂贵，目前服务器上已经有本地部署的ollama大模型了，我希望能对这个阶段做一些修改，让程序使用Selenium 从duckduckgo上检索学者个人主页，然后获取对应的html，将html中的可读部分的文字转化成markdown格式并截取前阈值个字符(截取到本地LLM输入阈值范围之内)，让本地llm去判断该学者的头衔。


# ✅ 学者主页正文抽取执行计划生成

---
## 🎯 任务目标
实现一个“自适应网页正文抽取流程”，用于抓取学者个人主页中的**学者简介正文（bio / profile）**，输出为 Markdown 格式。
目标是：
- 尽量避免使用 Playwright（节省成本）
- 优先使用静态 HTML
- 仅在必要时才使用浏览器渲染
- 避免抓取整页无关内容导致上下文过长
---
## 🧠 总体策略
采用两阶段策略：
### Phase 1 — 静态抓取（低成本优先）
1. 使用 `requests` 获取静态 HTML
2. 使用 `trafilatura.extract(output_format="html")` 抽取正文 HTML
3. 使用 `markdownify` 转为 Markdown
4. 将生成的 Markdown 交给 LLM 进行判定：
    判断标准：
    - 是否包含学者简介相关内容
    - 是否包含明显的 bio 结构（如教育背景、研究方向、职称等）
    - 文本长度是否合理（例如 > 200 字）
如果判断为“包含有效学者简介信息”：  
→ 直接输出结果，流程结束
如果判断为“未包含有效简介信息”：  
→ 进入 Phase 2
---
### Phase 2 — 动态渲染抓取（高成本 fallback）
1. 使用 Playwright 打开页面
2. 等待 `networkidle`
3. 获取渲染后的 HTML
4. 重复：
    - trafilatura 抽正文
    - markdownify 转 Markdown
    - LLM 判断是否包含有效学者简介
若成功 → 输出 Markdown  
若仍失败 → 返回空字符串或标记为 `NO_VALID_PROFILE_CONTENT`
---
## ⚙️ 约束条件
- 默认不保留图片
- 保留链接文本但可移除 URL
- 自动去除明显导航、页脚、菜单内容
- 输出 Markdown 仅包含：
    - 标题
    - 段落
    - 列表
- 不保留 HTML 标签
- 不输出整个页面 DOM
---
## 📦 输出要求
生成：
1. 执行流程步骤
2. 需要调用的工具列表
3. 判断逻辑说明
4. 异常处理策略
5. 成本控制说明
要求生成结构化执行计划，不要生成具体代码。
---

