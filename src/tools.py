import json
import pulp
import subprocess
from typing import Any, Dict, Union

def read_file(file_path: str) -> str:
    """读取指定文件的全部内容"""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def write_to_file(file_path: str, content: str) -> str:
    """将内容写入指定文件（支持 \\n 换行转义）"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content.replace("\\n", "\n"))
    return "写入成功"


def run_terminal_command(command: str) -> str:
    """执行终端命令，并返回成功/失败信息"""
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return "执行成功" if result.returncode == 0 else result.stderr


def solve_vm_scheduling_ilp(spec: Union[str, Dict[str, Any]]) -> str:
    """
    使用混合整数规划模型求解 VM–Host 调度问题。

    参数 spec 可以是 Python dict 或 JSON 字符串，字段包括：
    - hosts: [{"id": "H1", "cpu_cap"/"cpu_capacity": 32, "mem_cap"/"mem_capacity": 128, "oc_cpu": 1.0, "oc_mem": 1.0}, ...]
    - vms:   [{"id": "V1", "cpu": 8, "mem": 16, "cluster": null}, ...]
    - initial_placement: {"H1": ["V1","V2"], ...}
    - clusters: [{"id": "C1", "size": 2, "hard_excl": false}, ...]（如无可为空列表）
    - weights: {"alpha": 1.0, "beta": 1.0, "gamma": 0.0}

    返回值为 JSON 字符串，包含 assignment、host_util、migration、objective 等字段。
    """
    # 1）兼容 dict / str 两种调用方式
    if isinstance(spec, str):
        data = json.loads(spec)
    else:
        data = spec

    hosts = data["hosts"]
    vms = data["vms"]
    clusters = data.get("clusters", [])

    host_ids = [h["id"] for h in hosts]
    vm_ids = [v["id"] for v in vms]
    cluster_ids = [c["id"] for c in clusters]

    # ------- 参数映射（兼容 cpu_cap / mem_cap 命名）-------
    cpu_capacity = {}
    mem_capacity = {}
    oc_cpu = {}
    oc_mem = {}
    for h in hosts:
        hid = h["id"]
        cpu_capacity[hid] = h.get("cpu_capacity", h.get("cpu_cap"))
        mem_capacity[hid] = h.get("mem_capacity", h.get("mem_cap"))
        oc_cpu[hid] = h.get("oc_cpu", 1.0)
        oc_mem[hid] = h.get("oc_mem", 1.0)

    # VM 侧
    vm_cpu = {v["id"]: v["cpu"] for v in vms}
    vm_mem = {v["id"]: v["mem"] for v in vms}
    vm_cluster = {v["id"]: v.get("cluster") for v in vms}

    # ------- 用 initial_placement 推 orig_host -------
    orig_host = {v: None for v in vm_ids}
    init_placement = data.get("initial_placement", {})
    for h, vlist in init_placement.items():
        for v in vlist:
            orig_host[v] = h

    # 集群参数
    cluster_size = {c["id"]: c["size"] for c in clusters}
    cluster_hard_excl = {c["id"]: bool(c.get("hard_excl", False)) for c in clusters}

    # 每个集群包含哪些 VM
    cluster_vms = {cid: [] for cid in cluster_ids}
    for v in vm_ids:
        cid = vm_cluster.get(v)
        if cid in cluster_vms:
            cluster_vms[cid].append(v)

    # ------- 目标权重（兼容 alpha / beta / gamma 命名）-------
    weights = data.get("weights", {})
    alpha = float(weights.get("alpha_balance", weights.get("alpha", 1.0)))
    beta = float(weights.get("beta_migration", weights.get("beta", 1.0)))
    gamma = float(weights.get("gamma_soft", weights.get("gamma", 0.0)))

    # ------- 定义问题 -------
    prob = pulp.LpProblem("VM_Scheduling_Full_Model", pulp.LpMinimize)

    # ------- 决策变量 -------
    x = pulp.LpVariable.dicts(
        "x", (vm_ids, host_ids), lowBound=0, upBound=1, cat=pulp.LpBinary
    )
    y = pulp.LpVariable.dicts("y", host_ids, lowBound=0, upBound=1, cat=pulp.LpBinary)

    if cluster_ids:
        u = pulp.LpVariable.dicts(
            "u", (cluster_ids, host_ids), lowBound=0, upBound=1, cat=pulp.LpBinary
        )
        s = pulp.LpVariable.dicts("s", cluster_ids, lowBound=0, cat=pulp.LpContinuous)
    else:
        u = {}
        s = {}

    m = pulp.LpVariable.dicts("m", vm_ids, lowBound=0, upBound=1, cat=pulp.LpBinary)

    U = pulp.LpVariable.dicts("U", host_ids, lowBound=0, cat=pulp.LpContinuous)
    U_max = pulp.LpVariable("U_max", lowBound=0, cat=pulp.LpContinuous)
    U_min = pulp.LpVariable("U_min", lowBound=0, cat=pulp.LpContinuous)

    big_M = len(vm_ids)

    # ------- 约束 1：每 VM 恰好在一台 Host 上 -------
    for v in vm_ids:
        prob += pulp.lpSum(x[v][h] for h in host_ids) == 1, f"assign_{v}"

    # ------- 约束 2：Host 激活 -------
    for h in host_ids:
        prob += (
            pulp.lpSum(x[v][h] for v in vm_ids) <= big_M * y[h],
            f"host_active_{h}",
        )

    # ------- 约束 3：CPU / Mem 容量 -------
    for h in host_ids:
        prob += (
            pulp.lpSum(vm_cpu[v] * x[v][h] for v in vm_ids)
            <= cpu_capacity[h] * oc_cpu[h] * y[h],
            f"cpu_cap_{h}",
        )
        prob += (
            pulp.lpSum(vm_mem[v] * x[v][h] for v in vm_ids)
            <= mem_capacity[h] * oc_mem[h] * y[h],
            f"mem_cap_{h}",
        )

    # ------- 约束 4+5：集群 & 互斥 & 软约束 -------
    for cid in cluster_ids:
        vlist = cluster_vms[cid]
        if not vlist:
            prob += s[cid] == 0, f"empty_cluster_{cid}"
            continue

        for h in host_ids:
            prob += (
                pulp.lpSum(x[v][h] for v in vlist) >= u[cid][h],
                f"u_lb_{cid}_{h}",
            )
            prob += (
                pulp.lpSum(x[v][h] for v in vlist)
                <= len(vlist) * u[cid][h],
                f"u_ub_{cid}_{h}",
            )

            if cluster_hard_excl[cid]:
                prob += (
                    pulp.lpSum(x[v][h] for v in vlist) <= 1,
                    f"hard_excl_{cid}_{h}",
                )

        prob += (
            pulp.lpSum(u[cid][h] for h in host_ids) + s[cid] == cluster_size[cid],
            f"cluster_size_{cid}",
        )

    # ------- 约束 6：迁移计数 -------
    for v in vm_ids:
        h_orig = orig_host.get(v)
        if h_orig is None:
            prob += m[v] == 0, f"migration_none_{v}"
        else:
            prob += m[v] >= 1 - x[v][h_orig], f"migration_lb_{v}"

    # ------- 约束 7：负载均衡 U_h -------
    for h in host_ids:
        denom = cpu_capacity[h] * oc_cpu[h]
        if denom <= 0:
            prob += U[h] == 0, f"U_zero_{h}"
        else:
            prob += (
                pulp.lpSum(vm_cpu[v] * x[v][h] for v in vm_ids) == U[h] * denom,
                f"util_def_{h}",
            )
        prob += U[h] <= U_max, f"U_max_{h}"
        prob += U[h] >= U_min, f"U_min_{h}"

    # ------- 目标函数 -------
    obj_terms = [
        alpha * (U_max - U_min),
        beta * pulp.lpSum(m[v] for v in vm_ids),
    ]
    if cluster_ids:
        obj_terms.append(gamma * pulp.lpSum(s[cid] for cid in cluster_ids))

    prob += pulp.lpSum(obj_terms), "objective"

    # ------- 求解 -------
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    status = pulp.LpStatus[prob.status]
    objective = pulp.value(prob.objective)

    assignment = []
    for v in vm_ids:
        for h in host_ids:
            if pulp.value(x[v][h]) > 0.5:
                assignment.append({"vm": v, "host": h})
                break

    host_util = {h: float(pulp.value(U[h])) for h in host_ids}
    migration = {v: int(round(pulp.value(m[v]))) for v in vm_ids}

    soft_violation = {}
    if cluster_ids:
        for cid in cluster_ids:
            soft_violation[cid] = float(pulp.value(s[cid]))

    result = {
        "status": status,
        "objective": objective,
        "assignment": assignment,
        "host_util": host_util,
        "U_max": float(pulp.value(U_max)),
        "U_min": float(pulp.value(U_min)),
        "migration": migration,
        "soft_violation": soft_violation,
    }

    return json.dumps(result, ensure_ascii=False, indent=2)
