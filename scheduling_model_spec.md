# VM–Host 调度优化模型说明（Scheduling Model Spec）

本文档描述一个用于虚拟机（VM）在宿主机（Host）之间重新分布的混合整数规划模型。  
目标是在满足资源与集群约束的前提下，实现**负载均衡**、**尽量减少迁移**，并对**无法满足的互斥约束进行惩罚**。

---

## 1. 集合与索引

- $H$：宿主机集合（物理服务器），允许动态增删  
- $V$：虚拟机集合  
- $C$：集群集合（例如 $C=\{C_1,C_2,C_3,C_4\}$）  
- $V_c \subseteq V$：属于集群 $c$ 的 VM 子集  

索引约定：

- $h \in H$：宿主机索引  
- $v \in V$：虚拟机索引  
- $c \in C$：集群索引  

---

## 2. 参数（Parameters）

### 2.1 资源与集群参数

| 符号 | 含义 |
|------|------|
| $cpu_h$ | Host $h$ 的物理 CPU 容量 |
| $mem_h$ | Host $h$ 的物理内存容量 |
| $oc\_cpu$ | CPU 全局或按 host 的超卖系数（$>1$） |
| $oc\_mem$ | 内存全局或按 host 的超卖系数（$>1$） |
| $cpu_v$ | VM $v$ 所需的 CPU |
| $mem_v$ | VM $v$ 所需的内存 |
| $orig_{h,v}$ | 初始放置指示：若 VM $v$ 原本在 Host $h$ 上，则为 $1$，否则为 $0$ |
| $size_c$ | 集群 $c$ 要求的节点数（例如 $2,2,4,3$） |
| $hard\_excl_c$ | 集群 $c$ 是否为“硬互斥”集群，仅在 $c=\text{C4}$ 时为 `true` |

### 2.2 其他参数

| 符号 | 含义 |
|------|------|
| $M$ | 足够大的常数，用于“Host 激活”约束中的 Big-M 上界 |
| $\alpha$ | 负载均衡项的权重 |
| $\beta$ | 迁移次数惩罚项的权重 |
| $\gamma$ | 软约束违背惩罚项的权重 |

---

## 3. 决策变量（Decision Variables）

### 3.1 主决策变量

| 符号 | 类型 | 含义 |
|------|------|------|
| $x_{h,v}$ | 0/1 | 若 VM $v$ 被放置在 Host $h$，则为 $1$，否则为 $0$ |
| $y_h$ | 0/1 | Host $h$ 是否被激活（扩容/下线时使用），激活为 $1$，下线为 $0$ |
| $u_{c,h}$ | 0/1 | 在 Host $h$ 上是否至少有一个属于集群 $c$ 的 VM，模型中可由 $x_{h,v}$ 推导 |
| $m_v$ | 0/1 | VM $v$ 是否发生迁移，迁移过则为 $1$ |
| $s_c$ | 连续 $\ge 0$ | 集群 $c$ 的软约束违背程度（仅对硬互斥无法满足转为软时启用） |

### 3.2 负载均衡辅助变量

| 符号 | 类型 | 含义 |
|------|------|------|
| $U_h$ | 连续 | Host $h$ 的 CPU 利用率 |
| $U^{\max}$ | 连续 | 所有 Host 利用率的上界（最大值的线性化变量） |
| $U^{\min}$ | 连续 | 所有 Host 利用率的下界（最小值的线性化变量） |

---

## 4. 目标函数（Objective）

综合考虑三类目标：

1. **负载均衡**：最小化各宿主机 CPU 利用率的 max–min 区间 $(U^{\max} - U^{\min})$  
2. **迁移开销**：尽量减少发生迁移的 VM 数量 $\sum_v m_v$  
3. **软约束惩罚**：当互斥集群无法完全满足时，引入惩罚 $\sum_c s_c$

综合目标函数为：

\[
\min\; 
\alpha \cdot \left(U^{\max} - U^{\min}\right)
+ \beta \cdot \sum_{v \in V} m_v
+ \gamma \cdot \sum_{c \in C} s_c
\]

---

## 5. 约束条件（Constraints）

### 5.1 唯一放置约束：每台 VM 必须恰好在一台 Host 上

\[
\forall v \in V:\quad \sum_{h \in H} x_{h,v} = 1
\]

### 5.2 宿主机激活状态

若 Host 未激活，则不允许在其上放置任何 VM。使用 Big-M 线性化：

\[
\forall h \in H:\quad \sum_{v \in V} x_{h,v} \le M \cdot y_h
\]

直观解释：  
- $y_h = 0$ 时，右侧为 0，强制该 Host 上所有 $x_{h,v}=0$，表示下线。  
- $y_h = 1$ 时，该约束基本不生效，只起到上界作用。

### 5.3 CPU / Memory 容量与超卖约束

对每个 Host，所有 VM 的资源占用之和不得超过**可用资源 × 超卖系数 × 激活状态**。

CPU 约束：

\[
\forall h \in H:\quad
\sum_{v \in V} cpu_v \cdot x_{h,v}
\le
cpu_h \cdot oc\_cpu \cdot y_h
\]

内存约束：

\[
\forall h \in H:\quad
\sum_{v \in V} mem_v \cdot x_{h,v}
\le
mem_h \cdot oc\_mem \cdot y_h
\]

### 5.4 集群节点数（硬约束）

每个集群 $c$ 需要恰好部署在 $size_c$ 个不同的宿主机上。  
记 $u_{c,h}$ 表示“在 Host $h$ 上，是否存在至少一个属于集群 $c$ 的 VM”。

1. 节点数约束：

\[
\forall c \in C:\quad
\sum_{h \in H} u_{c,h} = size_c
\]

2. 定义 $u_{c,h}$ 与 $x_{h,v}$ 的关系：

\[
\forall c \in C,\ \forall h \in H,\ \forall v \in V_c:\quad
u_{c,h} \ge x_{h,v}
\]

并可通过下界约束保证一致性，例如：

\[
\forall c \in C,\ \forall h \in H:\quad
u_{c,h} \le \sum_{v \in V_c} x_{h,v}
\]

（实际实现时可以用 $\min(1,\sum x_{h,v})$ 的线性化形式。）

3. 对于标记为“硬互斥”的集群（当前仅 $C_4$）：

若 $hard\_excl_c = \text{true}$，则加入

\[
\forall h \in H:\quad u_{c,h} \le 1
\]

解释：每台 Host 最多承载该集群的 1 台 VM（或者等价地表示：该集群在任一 Host 上出现都被视为“占用一个节点”）。

> 备注：在实际 MIP 实现中，还可进一步细化约束，直接限制 $\sum_{v \in V_c} x_{h,v} \le 1$，效果更直接。

### 5.5 软约束（在硬互斥无法满足时转为软）

当无法完全满足互斥集群的节点分布时，引入非负罚变量 $s_c$：

\[
\forall c \in C \ \text{且}\ hard\_excl_c = \text{true}:\quad
s_c \ge size_c - \sum_{h \in H} u_{c,h}
\]

- 若所有节点数达标，则右侧 $\le 0$，$s_c$ 可取 0，不产生惩罚。  
- 若达不到要求，则 $s_c$ 至少补足缺口，并在目标函数中乘以权重 $\gamma$。

### 5.6 迁移计数约束（用于最小化迁移开销）

迁移变量 $m_v$ 表示“VM $v$ 是否经历了迁移”。  
若新的放置与原放置不一致，则需要 $m_v = 1$。

可以使用如下上界约束线性化：

\[
\forall v \in V,\ \forall h \in H:\quad
m_v \ge x_{h,v} - orig_{h,v}
\]

直观理解：

- 若 VM $v$ 未改变位置，则对所有 $h$，$x_{h,v} = orig_{h,v}$，右边为 $0$，$m_v$ 可以是 0；  
- 若某个 $h$ 上的状态由 0→1 或 1→0 发生变化，则存在 $x_{h,v}-orig_{h,v}=1$，强制 $m_v \ge 1$，即 $m_v=1$。

（实际实现中可以再加一些对称约束，使其既捕获“离开原 Host”又捕获“进入新 Host”，这里只保留核心形式。）

### 5.7 负载均衡约束（线性化 max–min）

定义每个 Host 的 CPU 利用率：

\[
\forall h \in H:\quad
U_h = \frac{\sum_{v \in V} cpu_v \cdot x_{h,v}}{cpu_h \cdot oc\_cpu}
\]

通过引入 $U^{\max}$ 与 $U^{\min}$ 两个变量，将“最大利用率”和“最小利用率”线性化：

\[
\forall h \in H:\quad
U_h \le U^{\max},\qquad
U_h \ge U^{\min}
\]

在目标函数中最小化 $U^{\max}-U^{\min}$ 即可推动所有 Host 的负载趋于均衡。

---

## 6. 模型总结

- **决策变量**：$\{x_{h,v}, y_h, u_{c,h}, m_v, s_c, U_h, U^{\max}, U^{\min}\}$  
- **主要约束**：  
  1. 每 VM 唯一放置  
  2. Host 激活 / 下线  
  3. CPU / Memory 容量 + 超卖  
  4. 集群节点数（硬约束）  
  5. 互斥集群的软约束罚分  
  6. 迁移计数  
  7. 负载均衡（max–min 线性化）  
- **目标函数**：在三个维度之间做权衡：  
  - CPU 利用率的均衡程度 $(U^{\max}-U^{\min})$  
  - 迁移次数 $\sum_v m_v$  
  - 互斥约束违背程度 $\sum_c s_c$

该说明可以作为 Agent 的“领域模型文档”，在 System Prompt 中引用其中的符号、约束和目标，提示大模型在调用求解工具（如 MILP 求解器、启发式算法脚本等）时遵守上述结构。
