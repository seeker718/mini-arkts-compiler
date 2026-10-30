"""IR Pass：标记「可跨设备执行」的函数，并生成 RPC 桩代码（实验三）。

对应大纲「分布式调度模拟」与方舟编译器分布式特性的思想：

1. **纯度分析**：一个函数若只做纯计算（不写字段、不写数组、不调用 IO），
   就可以标记为「可跨设备执行」，把它下沉到算力更强的远端设备；
2. **DeviceID 标注**：给这些函数分配一个目标设备（0 为本机，其余为远端）；
3. **RPC 桩生成**：为每个可跨设备函数生成一对代码——
   Skeleton 部署在远端设备上真正执行函数，Stub 部署在本机侧负责打包参数、
   经由「软总线」发送并取回结果。
"""

from __future__ import annotations

from . import ir

# 会产生副作用 / 依赖本机环境、不可跨设备执行的调用
_IMPURE_CALLEES = {
    "console.log", "log", "print", "alert",
    "Text", "Button", "Column", "Row",
}


def is_pure(func: ir.IRFunction) -> bool:
    """纯函数判定：无字段/数组写入、无对象构造、无 IO 调用。"""
    for ins in func.all_instructions():
        if ins.op in (ir.OP_FIELD_STORE, ir.OP_ARRAY_STORE, ir.OP_NEW):
            return False
        if ins.op == ir.OP_CALL:
            callee = ins.args[0]
            if callee in _IMPURE_CALLEES or callee.startswith("console"):
                return False
    return True


def mark_cross_device(module: ir.IRModule, remote_devices=(1, 2, 3)) -> ir.IRModule:
    """把纯函数标记为可跨设备执行，并轮转分配到远端设备。"""
    index = 0
    for func in module.functions:
        if func.is_method:
            continue
        if is_pure(func):
            func.cross_device = True
            func.device_id = remote_devices[index % len(remote_devices)]
            index += 1
    return module


def _c_func(name: str) -> str:
    return "ark_" + name.replace(".", "_")


def generate_rpc_stubs(module: ir.IRModule) -> str:
    """为所有可跨设备函数生成 C 语言的 RPC Stub / Skeleton 代码。"""
    targets = [f for f in module.functions if f.cross_device]
    lines = [
        "",
        "/* ============ 分布式软总线：RPC 桩（Stub / Skeleton） ============ */",
        "typedef struct {",
        "    int    from_device;",
        "    int    to_device;",
        "    char   func[64];",
        "    double args[8];",
        "    int    argc;",
        "    double result;",
        "} ArkRpcEnvelope;",
        "",
        "/* 模拟分布式软总线发送：本实验直接本地调用，等价于网络透传 */",
        "static ArkRpcEnvelope ark_softbus_send(ArkRpcEnvelope env) {",
        '    printf("[softbus] device %d -> device %d : %s\\n",',
        "           env.from_device, env.to_device, env.func);",
        "    return env;",
        "}",
    ]

    if not targets:
        lines.append("/* 本模块没有可跨设备执行的函数 */")
        return "\n".join(lines)

    for func in targets:
        count = len(func.params)
        params = ", ".join(f"double a{i}" for i in range(count))
        call_args = ", ".join(f"a{i}" for i in range(count))
        cf = _c_func(func.name)

        lines += [
            "",
            f"/* ---- {func.name}：可跨设备执行（目标 device={func.device_id}）---- */",
            f"/* Skeleton：部署在远端设备 {func.device_id} 上，真正执行计算 */",
            f"static double {cf}_skeleton({params or 'void'}) {{",
            f"    return {cf}({call_args});",
            "}",
            "",
            f"/* Stub：部署在本机侧，打包参数 -> 经软总线发送 -> 取回结果 */",
            f"static double {cf}_stub(int target_device{', ' + params if params else ''}) {{",
            "    ArkRpcEnvelope env;",
            "    memset(&env, 0, sizeof(env));",
            "    env.from_device = 0;",
            "    env.to_device = target_device;",
            f'snprintf(env.func, sizeof(env.func), "%s", "{func.name}");',
        ]
        for i in range(count):
            lines.append(f"    env.args[{i}] = a{i};")
        lines += [
            f"    env.argc = {count};",
            f"    env.result = {cf}_skeleton({call_args});",
            "    env = ark_softbus_send(env);",
            "    return env.result;",
            "}",
        ]

    return "\n".join(lines)


def cross_device_report(module: ir.IRModule) -> str:
    """生成可读的跨设备分析报告。"""
    lines = ["可跨设备执行的函数分析", "-" * 40]
    for func in module.functions:
        mark = "可跨设备" if func.cross_device else "仅本机"
        dev = f"device={func.device_id}" if func.cross_device else "-"
        reason = "纯计算，无副作用" if func.cross_device else _reason(func)
        lines.append(f"  {func.name:<20} {mark:<8} {dev:<12} {reason}")
    return "\n".join(lines)


def _reason(func: ir.IRFunction) -> str:
    if func.is_method:
        return "类方法，依赖实例状态"
    for ins in func.all_instructions():
        if ins.op == ir.OP_FIELD_STORE:
            return "写对象字段"
        if ins.op == ir.OP_ARRAY_STORE:
            return "写数组元素"
        if ins.op == ir.OP_NEW:
            return "构造对象"
        if ins.op == ir.OP_CALL and ins.args[0] in _IMPURE_CALLEES:
            return f"调用 {ins.args[0]}"
    return "含其他副作用"