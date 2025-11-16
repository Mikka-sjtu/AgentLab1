from pathlib import Path

from src import (
    ReActAgent,
    read_file,
    run_terminal_command,
    solve_vm_scheduling_ilp,
    write_to_file,
)

def main() -> None:
    project_dir = str(Path(__file__).resolve().parents[1])

    tools = [read_file, write_to_file, run_terminal_command, solve_vm_scheduling_ilp]
    agent = ReActAgent(
        tools=tools,
        project_directory=project_dir,
    )

    question = """
当前集群的初始状态如下：

- 有 4 台宿主机 Host-1 ~ Host-4，规格为：
  - H1: cpu_cap = 32, mem_cap = 128
  - H2: cpu_cap = 32, mem_cap = 128
  - H3: cpu_cap = 32, mem_cap = 128
  - H4: cpu_cap = 32, mem_cap = 128

- 有 8 台 VM，初始放置情况为（括号内为所在宿主机）：
  - V1: cpu = 8,  mem = 16, 在 H1
  - V2: cpu = 8,  mem = 16, 在 H1
  - V3: cpu = 8,  mem = 16, 在 H2
  - V4: cpu = 8,  mem = 16, 在 H2
  - V5: cpu = 8,  mem = 16, 在 H3
  - V6: cpu = 8,  mem = 16, 在 H3
  - V7: cpu = 8,  mem = 16, 在 H4
  - V8: cpu = 8,  mem = 16, 在 H4

现在新增一台宿主机 H5，希望在满足资源约束的前提下，对 VM 做一次 rebalance：

【硬约束】
- 每个 VM 必须恰好落在一台 Host 上；
- 每台 Host 上所有 VM 的 CPU / Mem 总和不能超过该 Host 的容量。

【优化目标】
- 各 Host 的 CPU 利用率尽量均衡；
- 发生迁移的 VM 数量尽量少。
"""

    answer = agent.run(question)
    print("\n========= Final Answer =========\n")
    print(answer)


if __name__ == "__main__":
    main()
