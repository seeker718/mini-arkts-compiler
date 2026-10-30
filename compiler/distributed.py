"""分布式调度模拟（实验三）。

模型包含三部分：
    * :class:`DeviceNode`  —— 模拟的设备节点，各有不同的 CPU 速度、内存与网络延迟；
    * :class:`TaskUnit`    —— 由 IR 指令序列拆分出的可独立调度任务单元（以函数为粒度）；
    * :func:`schedule`     —— 调度器，支持轮询、最短队列优先与数据本地化三种策略。

模拟执行时，每个设备串行执行分配给它的任务，耗时 = 计算量 / CPU 速度（跨设备再加网络延迟），
从而得到各设备负载与整体工期（makespan），用于比较不同策略的优劣。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import ir


@dataclass
class DeviceNode:
    id: int
    name: str
    cpu_speed: float = 1.0        # 相对速度，越大越快
    memory_mb: int = 1024
    network_latency_ms: float = 5.0


@dataclass
class TaskUnit:
    id: int
    name: str
    function: str
    cost: float                   # 相对计算量（以 IR 指令条数为度量）
    data_device: int = 0          # 数据所在设备（供数据本地化策略使用）
    prefer_device: int = 0        # 建议执行设备（来自 IR 的 device 标注）


@dataclass
class ScheduleResult:
    strategy: str
    assignments: list = field(default_factory=list)   # [(task_id, task_name, device_id)]
    device_tasks: dict = field(default_factory=dict)
    device_load: dict = field(default_factory=dict)
    makespan: float = 0.0
    balance: float = 1.0

    def report(self) -> str:
        lines = [f"调度策略: {self.strategy}", "-" * 56]
        for device_id in sorted(self.device_load):
            load = self.device_load[device_id]
            tasks = self.device_tasks.get(device_id, [])
            lines.append(
                f"  设备 {device_id}: 负载 {load:8.2f}  任务数 {len(tasks):2d}  "
                f"任务 {tasks}"
            )
        lines.append("-" * 56)
        lines.append(f"  总工期(makespan): {self.makespan:.2f}")
        lines.append(f"  负载均衡度(balance): {self.balance:.3f}  (1.0 表示完全均衡)")
        return "\n".join(lines)


def default_devices() -> list[DeviceNode]:
    """默认的设备拓扑：一台手机 + 平板 + 智慧屏 + 手表。"""
    return [
        DeviceNode(0, "手机(本机)", cpu_speed=2.0, memory_mb=4096, network_latency_ms=0.0),
        DeviceNode(1, "平板", cpu_speed=1.5, memory_mb=8192, network_latency_ms=5.0),
        DeviceNode(2, "智慧屏", cpu_speed=1.2, memory_mb=16384, network_latency_ms=8.0),
        DeviceNode(3, "手表", cpu_speed=0.7, memory_mb=1024, network_latency_ms=12.0),
    ]


def tasks_from_module(module: ir.IRModule, device_count: int = 4) -> list[TaskUnit]:
    """把 IR 模块按「函数」粒度拆分为任务单元。

    计算量用函数的 IR 指令条数度量，这是最简单也最直观的拆分方式；
    数据本地化信息取自函数所标注的 device。
    """
    tasks: list[TaskUnit] = []
    for index, func in enumerate(module.functions):
        cost = float(max(func.instruction_count(), 1))
        prefer = func.device_id % device_count if device_count > 0 else 0
        tasks.append(
            TaskUnit(
                id=index,
                name=func.name,
                function=func.name,
                cost=cost,
                data_device=prefer,
                prefer_device=prefer,
            )
        )
    return tasks


def schedule(tasks: list[TaskUnit], devices: list[DeviceNode],
             strategy: str = "least_loaded") -> ScheduleResult:
    """按指定策略把任务分配到设备上，并模拟执行统计负载。"""
    if not devices:
        raise ValueError("至少需要一个设备节点")

    device_load = {d.id: 0.0 for d in devices}
    device_tasks = {d.id: [] for d in devices}
    speed = {d.id: max(d.cpu_speed, 0.01) for d in devices}
    latency = {d.id: d.network_latency_ms / 1000.0 for d in devices}
    by_id = {d.id: d for d in devices}
    assignments: list[tuple] = []

    ordered = sorted(tasks, key=lambda t: -t.cost)  # 长任务优先分配

    def assign(task: TaskUnit, device_id: int) -> None:
        penalty = latency[device_id] if task.data_device != device_id else 0.0
        device_load[device_id] += task.cost / speed[device_id] + penalty
        device_tasks[device_id].append(task.id)
        assignments.append((task.id, task.name, device_id))

    if strategy == "round_robin":
        for i, task in enumerate(ordered):
            assign(task, devices[i % len(devices)].id)
    elif strategy == "data_locality":
        for task in ordered:
            target = task.data_device if task.data_device in by_id else None
            if target is None:
                target = min(devices, key=lambda d: device_load[d.id]).id
            assign(task, target)
    else:  # least_loaded（最短队列优先）
        for task in ordered:
            target = min(devices, key=lambda d: device_load[d.id]).id
            assign(task, target)

    loads = list(device_load.values())
    makespan = max(loads) if loads else 0.0
    balance = 1.0 - (max(loads) - min(loads)) / makespan if makespan > 0 else 1.0

    return ScheduleResult(
        strategy=strategy,
        assignments=assignments,
        device_tasks=device_tasks,
        device_load=device_load,
        makespan=makespan,
        balance=balance,
    )


def compare_strategies(tasks: list[TaskUnit], devices: list[DeviceNode]) -> dict:
    """对三种策略各跑一次，返回对比结果（供报告第 5 点分析）。"""
    strategies = ["round_robin", "least_loaded", "data_locality"]
    return {name: schedule(tasks, devices, name) for name in strategies}