# PaperCitedRemarkAnalysis

End-to-end pipeline to analyze how influential citations (Fellow authors) refer to a target paper.
Given a target paper title, the system pulls citing papers, filters for published works,
checks Fellow status for top authors, extracts citation contexts from PDFs, scores each
context with an LLM, and outputs reports plus trace logs for reproducibility.

## 目录

- 项目简介
- 主要特性
- 流程概览
- 环境要求
- 安装与配置
- 快速开始
- 结果输出
- 常见问题

## 项目简介

本项目用于对指定目标论文进行引文分析，重点关注高影响力作者（如 IEEE/ACM/AAAI Fellow）在引用时的观点和语义倾向。系统会自动拉取引用论文、筛选已发表作品、识别高影响力作者、抽取 PDF 引文上下文，并通过 LLM 进行评分，最终产出可追溯的报告与日志。

## 主要特性

- 自动检索目标论文及其引用论文
- 作者学术指标补全与 Fellow 身份校验
- PDF 全文提取与引文上下文抽取
- LLM 评分与报告生成
- 全流程 trace 日志便于复现实验

## 流程概览（T1-T9）

1. RunContext 初始化与参数快照（run_id、目录、trace）
2. OpenAlex 标题匹配（目标论文 id/doi）
3. Cited-by 拉取（TopK）
4. DBLP 发表状态校验（仅保留已发表）
5. 作者指标补全（h-index、机构）
6. TopK 作者 Fellow 校验（IEEE/ACM/AAAI）
7. 候选论文选择与回退策略（max h-index）
8. PDF 下载、全文提取、引文上下文抽取
9. LLM 评分与报告输出（单篇报告 + 汇总报告）

## 环境要求

- Linux 环境
- Conda
- Python 3.10
- Chrome 与 Chromedriver（用于 `pcra.get_pdf`）
- minerU 服务（用于 PDF 结构化解析，建议 5GB GPU 显存）
- 可访问 DuckDuckGo 的网络环境（需要代理）

## 安装与配置

### 1. Python 环境与依赖

```bash
conda create -n pcraPaper python=3.10
conda activate pcraPaper
pip install -r requirements.txt
```

### 2. Chrome / Chromedriver 安装（Selenium）

`pcra.get_pdf` 需要 Chrome 与 chromedriver 二进制文件，路径固定在仓库根目录下：

- `chrome_bin/chrome-linux64/chrome`
- `chrome_bin/chromedriver-linux64/chromedriver`

这两个文件来自 **Chrome for Testing** 官方发行包。请下载相同版本的
`chrome-linux64.zip` 与 `chromedriver-linux64.zip` 并解压到 `chrome_bin/`。

示例（可替换版本号）：

```bash
VER=143.0.7499.40
mkdir -p chrome_bin
wget -O /tmp/chrome-linux64.zip "https://storage.googleapis.com/chrome-for-testing-public/${VER}/linux64/chrome-linux64.zip"
wget -O /tmp/chromedriver-linux64.zip "https://storage.googleapis.com/chrome-for-testing-public/${VER}/linux64/chromedriver-linux64.zip"
unzip -q /tmp/chrome-linux64.zip -d chrome_bin
unzip -q /tmp/chromedriver-linux64.zip -d chrome_bin
```

验证版本：

```bash
chrome_bin/chrome-linux64/chrome --version
chrome_bin/chromedriver-linux64/chromedriver --version
```

### 3. minerU 环境安装与服务启动

```bash
conda create -n MinerUService python=3.12
conda activate MinerUService

export UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/

pip install uv -i https://pypi.org/simple/
uv pip install "mineru[core]"

# 首次运行时指定镜像站下载必要的模型文件，然后转换一个文件触发所有模型的下载
export MINERU_MODEL_SOURCE=modelscope
mineru -p <input_path> -o <output_path>

# 找一个存储临时文件的目录，在这里启动 minerU
cd <minerUtemp>
export MINERU_MODEL_SOURCE=modelscope
mineru-api --host 0.0.0.0 --port 18543
```

服务端口：`18543`。

### 4. LLM API Key 配置

找到配置文件 `config/llm_model_template.yaml`：

```bash
cp config/llm_model_template.yaml config/llm_model.yaml
```

填写你的 OpenRouter API Key。`api_key_env` 和 `api_key` 的值保持一致即可。
`openrouter_web_search` 字段必须使用 OpenRouter 模型，`text` 字段可以使用其他与 OpenAI 接口兼容的模型。

## 快速开始

### 1. 单篇论文引文分析

```bash
conda activate pcraPaper
bash e2e_scripts/run_one_paper/run_one_paper.sh
```

运行前请在 `e2e_scripts/run_one_paper/run_one_paper.sh` 中设置以下变量：

```bash
# 目标论文(被引用)名称
PAPER_TO_ANALYZE="Efficient Personalized PageRank Computation: The Power of Variance-Reduced Monte Carlo Approaches"
# 目标论文作者
TARGET_AUTHOR="Rong-Hua Li"
# 要忽略的作者（不会分析作者列表中包含被忽略作者的 citing paper）
IGNORE_AUTHORS='["Guoren Wang","Rong-Hua Li"]'
# 指定的 ID，便于后续聚合统计
RUN_ID="102"
```

默认结果存储位置：`trace_log/`。
建议使用 `tmux` 后台运行，单篇分析约 5 分钟左右。

### 2. 多篇论文结果汇总

将 `trace_log/` 目录下的结果汇总成 Excel：

```bash
conda activate pcraPaper
python e2e_scripts/export_result/export_summary_to_excel.py
```

## 结果输出

单篇论文的结果和日志位于 `trace_log/<target_paper_name>/`：

- `res/paper_ref_contexts/{paper_id}.json`（PDF、全文、引文上下文）
- `res/paper_ref_contexts_scored/{paper_id}.json`（LLM 评分）
- `res/fulltext/{paper_id}.md`
- `res/pdf/{paper_id}.pdf`
- `res/reports/paper/{paper_id}.md`
- `res/reports/summary.md`
- `res/summary.json`
- `log/{run_id}.ndjson`（阶段 trace 日志）

多篇论文汇总的结果默认位于 ： `e2e_scripts/export_result`

## 常见问题

- 无法访问 DuckDuckGo：请配置代理并设置相关环境变量。
- Chrome 或 Chromedriver 版本不匹配：确保两者版本号一致，并放在 `chrome_bin/`。
- minerU 服务不可用：确认端口 `18543` 已启动，且运行环境可访问 GPU。
