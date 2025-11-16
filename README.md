# 项目简介

- 使用 ReAct 框架：让大模型在「思考 – 行动 – 观察」循环中调用工具。
- 提供一个简化的 VM–Host 调度 ILP 模型作为示例场景。
- 支持多种工具调用：
  - 读取文件（调度模型说明等）
  - 写入文件
  - 运行终端命令
  - 调用 `solve_vm_scheduling_ilp` 进行调度求解

# 安装与环境准备

### 安装依赖
pip install -r requirements.txt

### 配置 OpenRouter API Key
在终端中设置环境变量：
- Linux / macOS：
export OPENROUTER_API_KEY="sk-你的-key"
- Window PowerShells：
$env:OPENROUTER_API_KEY="sk-你的-key"

# 运行示例
### 运行命令行 Demo
python examples/demo.py
终端中会看到类似下面的输出流程：
- Thought（思考）
- Action（工具调用）
- Observation（观察结果）
- 最终给出一个 VM–Host 调度方案，以及迁移情况和各 Host 的负载

### 使用 Jupyter Notebook
如果你更习惯 Notebook，可以打开：
react_agent.ipynb
里面是最初的原型代码，方便你一步步看清楚每个单元格做了什么。

# 注意事项
- ReAct 提示词、工具集合以及权重配置（alpha / beta / gamma）都可以自由修改。
- 若要接入其他模型（例如不同的 OpenRouter 模型），可以在 settings.py 中调整默认模型名称。
- 本地Excel资源数据自动读取还未实现
