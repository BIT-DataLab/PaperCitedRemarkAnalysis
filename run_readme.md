
# 一键运行脚本

## llm api key配置

找到配置文件config/llm_model_template.yaml
cp config/llm_model_template.yaml  config/llm_model.yaml
然后填写你的openrouter api key, 其中api_key_env 和 api_key的值保持一致即可。
openrouter_web_search 字段必须使用openrouter模型， text字段可以使用其他与openai接口兼容的模型。

## 获取针对单篇论文的引文分析结果

```
conda activate pcraPaper
bash e2e_scripts/run_one_paper/run_one_paper.sh
```


运行前针对 e2e_scripts/run_one_paper/run_one_paper.sh 需要设置一些变量，来指定对单篇目标论文的参数。
```sh

# User config: update only these 4 values.
# 目标论文(被引用)名称
PAPER_TO_ANALYZE="Efficient Personalized PageRank Computation: The Power of Variance-Reduced Monte Carlo Approaches"
# 目标论文作者
TARGET_AUTHOR="Rong-Hua Li"
# 要忽略的作者（不会分析作者列表中包含被忽略作者的citing paper）
IGNORE_AUTHORS='["Guoren Wang","Rong-Hua Li"]'
# 指定的ID, 便于后续聚合成excel时的统计。
RUN_ID="102"

```

默认结果存储位置：
trace_log/

该脚本建议使用tmux挂在后台运行，因为单篇论文分析时间在5min左右。
该脚本运行需要代理服务/海外网络环境来访问duckduckgo搜索引擎服务，请自行配置代理服务后设置环境变量以使用代理（本仓库不提供任何代理使用的内容）。

## 多篇论文分析结果汇总
将默认结果存储位置的结果汇总成excel表格：
conda activate pcraPaper
python e2e_scripts/export_result/export_summary_to_excel.py
