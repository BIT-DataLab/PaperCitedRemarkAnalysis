
# pcraPaper本体conda环境安装

conda create -n py310 python=3.10
pip install -r requirements.txt

# minerU环境安装和服务启动
(需要5GB的GPU显存)

```
conda create -n MinerUService python=3.12

conda activate MinerUService

export UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/

pip install uv -i https://pypi.org/simple/
uv pip install "mineru[core]"

# 首次运行时指定镜像站下载必要的模型文件，然后转换一个文件触发所有模型的下载
export MINERU_MODEL_SOURCE=modelscope
# <input_path>是pdf文件路径+文件名， <output_path>是转换后文件保存路径
mineru -p <input_path> -o <output_path>

# 找一个存储临时文件的目录，在这里启动minerU。
cd <minerUtemp>
export MINERU_MODEL_SOURCE=modelscope
mineru-api --host 0.0.0.0 --port 18543
# 等命令启动完成后，即可运行引文分析主程序。（建议使用tmux启动，避免前台退出导致不可用）
```

服务端口：18543