"""实验三报告正文（严格对应大纲的 6 条报告要求）。

    1 内容简介                          —— 要求 1（IR 的重要性）
    2 实验上机试题
    3 算法实现
        3.1 IR 设计方案与特点            —— 要求 1
        3.2 AST -> IR 的转换规则         —— 要求 2
        3.3 关键数据结构与核心实现代码   —— 要求 2
        3.4 分布式调度模拟的模型设计     —— 要求 3
        3.5 调度策略与模拟流程           —— 要求 3
        3.6 实现结果：IR 示例与调度数据  —— 要求 4
    4 测试
    5 调度策略优劣分析与鸿蒙应用场景    —— 要求 5
    6 实验总结与改进方向                —— 要求 6
"""

from __future__ import annotations

TABLE_IR = (
    ["用例编号", "测试项", "测试步骤", "预期结果", "测试结果"],
    [
        ["1", "合法输入：基本运算", "function add(a: number, b: number): number { return a + b; }",
         "生成 IRFunction add，含 %t1 = add %p0_a, %p1_b 与 ret %t1", "通过"],
        ["2", "等价类：变量重赋值（SSA）", "let x: number = 1; x = 2; return x;",
         "产生两个版本 %x 与 %x.2，后续引用指向 %x.2", "通过"],
        ["3", "边界值：if 无 else", "if (c) { x = 2; }",
         "仍生成 if.else 空块，并在汇合处插入 φ", "通过"],
        ["4", "分支与 φ 函数", "if (c) { x = 2; } else { x = 3; } return x;",
         "生成 if.then / if.else / if.end 三块，汇合块含 phi 指令", "通过"],
        ["5", "循环结构：while", "while (i < n) { s = s + i; i++; }",
         "生成 while.cond / while.body / while.end 三块与 jmp 回边", "通过"],
        ["6", "循环结构：for", "for (let i = 0; i < n; i++) { ... }",
         "生成 for.cond / for.body / for.update / for.end 四块", "通过"],
        ["7", "函数调用", "return g(1);", "生成 %t = call g(1)", "通过"],
        ["8", "类方法", "class C { v: number = 0; get(): number { return this.v; } }",
         "生成 IRFunction C.get，方法带隐含 %this", "通过"],
        ["9", "边界值：声明式 UI", "build() { Column() { Text('hi') } }",
         "不生成计算型 IR（跳过），不报错", "通过"],
    ],
    [1.3, 2.6, 5.0, 5.3, 1.4],
)

TABLE_SCHED = (
    ["用例编号", "测试项", "测试步骤", "预期结果", "测试结果"],
    [
        ["1", "输入合法值：任务拆分", "对含 4 个函数的模块调用 tasks_from_module",
         "得到 4 个任务单元，cost 等于各自 IR 指令条数（如 a=11、c=21）", "通过"],
        ["2", "输入合法值：全部任务被分配", "对三种策略分别调用 schedule",
         "每种策略下任务编号集合都等于 {0..n-1}，无遗漏", "通过"],
        ["3", "等价类：轮询策略", "4 个等长任务 + 4 个设备，round_robin",
         "按顺序分配到设备 0,1,2,3", "通过"],
        ["4", "等价类：数据本地化", "3 个 data_device=2 的任务 + data_locality",
         "全部落到设备 2", "通过"],
        ["5", "边界值：空任务集", "schedule([])",
         "makespan=0.0、balance=1.0，不抛异常", "通过"],
        ["6", "指标有效性", "对正常任务集调度",
         "makespan>0 且 0<balance<=1.0", "通过"],
    ],
    [1.3, 2.6, 5.0, 5.3, 1.4],
)

TABLE_CGEN = (
    ["用例编号", "测试项", "测试步骤", "预期结果", "测试结果"],
    [
        ["1", "生成运行时前导", "任意函数生成 C",
         "含 #include <stdio.h> 与 ark_console_log_number 等运行时桩", "通过"],
        ["2", "函数命名约定", "function add(...)",
         "C 函数名为 ark_add（模拟鸿蒙 API 命名）", "通过"],
        ["3", "生成 main 入口", "function demo(): number",
         "生成 int main(void) 并调用 ark_demo()", "通过"],
        ["4", "φ 消除（out-of-SSA）", "含 if/else 的函数",
         "C 中不出现 phi，改用 goto 标签 + 前驱块赋值", "通过"],
        ["5", "字符串拼接", 'return "a" + "b";', "调用运行时桩 ark_str_concat", "通过"],
        ["6", "类字段访问", "class P { x: number; get(){ return this.x; } }",
         "生成 typedef struct P 与 self->x 访问，方法为 ark_P_get(P* self)", "通过"],
        ["7", "边界值：未解析外部调用", "调用模块内不存在的函数",
         "生成容错代码（返回 0 并注释），不产生非法 C", "通过"],
    ],
    [1.3, 2.6, 5.0, 5.3, 1.4],
)

CODE_IR_STRUCT = '''@dataclass
class IRInstruction:
    op: str                    # assign / add / sub / br / jmp / phi / call / ret ...
    dst: str | None = None     # 目标操作数，如 "%t1"
    args: list = None          # 源操作数，如 ["%a", "%b"]
    device: int = 0            # DeviceID 维度：0=本机，其余=模拟的远端设备

@dataclass
class IRFunction:
    name: str
    params: list = []          # 形参的 IR 名
    return_type: str = "void"
    blocks: list = []          # IRBasicBlock 列表
    local_types: dict = {}     # 局部变量 IR 名 -> 源语言类型（供 C 代码生成）
    device_id: int = 0         # 建议执行设备
    cross_device: bool = False # 是否可跨设备执行（由分布式 Pass 标注）
    is_method: bool = False'''

CODE_GEN_FUNCTION = '''def _gen_function(self, node, owner=None):
    """把函数 / 方法翻译成一个 IRFunction。"""
    name = f"{owner}.{node.name}" if owner else node.name
    func = ir.IRFunction(name=name, return_type=..., is_method=owner is not None)
    self.func, self.env, self.versions = func, {}, {}

    # 形参重命名为 IR 名，并建立「源变量名 -> IR 名」的映射
    for i, param in enumerate(node.params):
        pname = f"%p{i}_{self._sanitize(param.name)}"
        func.params.append(pname)
        self.env[param.name] = pname

    if owner is not None:              # 方法是带隐含 %this 的函数
        self.env["this"] = "%this"

    self._start_block("entry")         # 入口基本块
    self._stmt_list(node.body.body)    # 逐条语句下降生成指令
    self._ensure_return()              # 末尾没有 ret 时补一条
    self.module.functions.append(func)'''

CODE_SSA = '''def _define(self, name, value, type_name, lineno=0):
    """变量赋值 —— SSA 版本命名的核心。"""
    count = self.versions.get(name, 0) + 1
    self.versions[name] = count
    ir_name = f"%{name}" if count == 1 else f"%{name}.{count}"  # %x -> %x.2 -> %x.3
    self.env[name] = ir_name            # 之后对该变量的引用都取最新版本
    self.func.local_types[ir_name] = type_name
    self._emit(ir.OP_ASSIGN, dst=ir_name, args=[value])
    return ir_name'''

CODE_IF_PHI = '''def _s_IfStatement(self, node):
    cond = self._expr(node.test)
    then_label = self._new_label("if.then")
    else_label = self._new_label("if.else")
    end_label  = self._new_label("if.end")
    self._emit(ir.OP_BR, args=[cond, then_label, else_label])

    before = dict(self.env)                       # 记录分支前的变量版本

    self._start_block(then_label)
    self.env = dict(before)
    self._stmt(node.consequent)
    self._emit(ir.OP_JMP, args=[end_label])
    then_env, then_end = dict(self.env), self.block.label

    self._start_block(else_label)
    self.env = dict(before)
    if node.alternate is not None:
        self._stmt(node.alternate)
    self._emit(ir.OP_JMP, args=[end_label])
    else_env, else_end = dict(self.env), self.block.label

    self._start_block(end_label)
    self.env = dict(before)
    self._merge_phi(before, then_env, else_env, then_end, else_end)   # 插入 φ

def _merge_phi(self, before, then_env, else_env, then_end, else_end):
    """对在两条路径上取到不同版本的变量，插入 φ 指令合并。"""
    for name in sorted(set(then_env) | set(else_env)):
        t = then_env.get(name, before.get(name))
        e = else_env.get(name, before.get(name))
        if t is None or e is None or t == e:   # 两分支版本一致，无需合并
            continue
        phi = self._new_var(name)              # 产生一个新版本，如 %result.4
        self._emit(ir.OP_PHI, dst=phi, args=[(t, then_end), (e, else_end)])'''

CODE_CGEN_PHI = '''def _emit_instruction(self, ins, block_label):
    if ins.op == ir.OP_PHI:
        return []          # φ 本身不生成任何代码，交给前驱块处理
    ...

def _phi_assignments(self, target_label, pred_label):
    """out-of-SSA：在跳转到 target 之前，把该边对应的实参写入 φ 的目标变量。"""
    block = self.func.block(target_label)
    stmts = []
    for ins in block.instructions:
        if ins.op != ir.OP_PHI:
            continue
        for value, label in ins.args:
            if label == pred_label:
                stmts.append(f"{self._operand(ins.dst)} = {self._operand(value)};")
                break
    return stmts

# 遇到 jmp / br 时，先插入目标块 φ 的赋值，再 goto
#   if (cond) { phi_x = v_x; goto L_if_then; } else { phi_x = v_x_1; goto L_if_else; }'''

CODE_SCHEDULE = '''def schedule(tasks, devices, strategy="least_loaded"):
    device_load = {d.id: 0.0 for d in devices}
    speed  = {d.id: max(d.cpu_speed, 0.01) for d in devices}
    latency = {d.id: d.network_latency_ms / 1000.0 for d in devices}

    ordered = sorted(tasks, key=lambda t: -t.cost)   # 长任务优先分配

    for task in ordered:
        if strategy == "round_robin":
            target = devices[index % len(devices)].id
        elif strategy == "data_locality":
            target = task.data_device           # 优先数据所在设备
        else:                                    # least_loaded：最短队列优先
            target = min(devices, key=lambda d: device_load[d.id]).id

        penalty = latency[target] if task.data_device != target else 0.0
        device_load[target] += task.cost / speed[target] + penalty

    makespan = max(device_load.values())                       # 总工期
    balance  = 1 - (max(loads) - min(loads)) / makespan        # 负载均衡度
    return ScheduleResult(strategy, ..., makespan, balance)'''

OUT_IR = '''$ python main.py ir samples/ir_demo.ets

func classify(%p0_value) -> number {
entry:
  %result = assign 1
  %t1 = gt %p0_value, 100
  br %t1, if.then.1, if.else.2
if.then.1:
  %result.2 = assign 2          <- 变量新版本（SSA）
  jmp if.end.3
if.else.2:
  %t2 = add %result, 0
  %result.3 = assign %t2
  jmp if.end.3
if.end.3:
  %result.4 = phi [%result.2, if.then.1], [%result.3, if.else.2]   <- φ 合并
  ret %result.4
}

（模块共 4 个函数，10 个基本块，33 条 IR 指令）'''

OUT_SCHED = '''$ python build_ir.py     # 调度模拟部分

可跨设备执行的函数分析
----------------------------------------
  square     可跨设备 device=1  纯计算，无副作用
  sumTo      可跨设备 device=2  纯计算，无副作用
  classify   可跨设备 device=3  纯计算，无副作用
  demo       可跨设备 device=1  纯计算，无副作用

[round_robin]    makespan=8.34  balance=0.344  负载={0:5.50, 1:6.67, 2:8.34, 3:2.87}
[least_loaded]   makespan=8.34  balance=0.344  负载={0:5.50, 1:6.67, 2:8.34, 3:2.87}
[data_locality]  makespan=14.29 balance=0.000  负载={0:0.00, 1:8.00, 2:9.17, 3:14.29}'''

OUT_RPC = '''// out/ir_demo.c 中的分布式桩（节选）
/* Skeleton：部署在远端设备 1 上，真正执行计算 */
static double ark_square_skeleton(double a0) {
    return ark_square(a0);
}
/* Stub：部署在本机侧，打包参数 -> 经软总线发送 -> 取回结果 */
static double ark_square_stub(int target_device, double a0) {
    ArkRpcEnvelope env;
    memset(&env, 0, sizeof(env));
    env.from_device = 0;
    env.to_device = target_device;
    snprintf(env.func, sizeof(env.func), "%s", "square");
    env.args[0] = a0;
    env.argc = 1;
    env.result = ark_square_skeleton(a0);
    env = ark_softbus_send(env);
    return env.result;
}'''

CONTENT = [
    ("title", "实验三  中间表示（IR）生成与分布式调度模拟"),

    # ---------------------------------------------------------- 要求 1
    ("h1", "1 内容简介"),
    ("p", "中间表示（IR）是编译器前端与后端之间的桥梁，也是所有中端优化的载体。"
          "源语言种类繁多，目标机器架构各异，若直接由 AST 生成机器码，则「m 种前端 × n 种后端」"
          "需要 m×n 套代码；引入一层与源语言和目标机器都无关的 IR 之后，"
          "只需「前端 → IR」与「IR → 后端」两套，复杂度降到 m+n。"
          "此外，优化（常量折叠、死代码消除、循环优化、内联等）都是在 IR 上完成的——"
          "IR 是编译器「可优化的公共语言」。常见的 IR 形式有三地址码、四元式、DAG 与 SSA 形式。"),
    ("p", "本实验为 ArkTS 子集设计并实现了一种三地址码 IR，并在此基础上模拟了鸿蒙分布式场景下的任务调度。"
          "所选 IR 方案的特点可归纳为四点："),
    ("bullets", [
        "三地址码 + 基本块：每条指令至多一个目标值、最多两个源操作数，"
        "并以基本块为单位配合 br / jmp 与标签表达顺序、分支与循环，结构接近 LLVM IR，易于后端翻译；",
        "DeviceID 维度：每条指令与每个函数都带 device 字段（0 为本机，其余为模拟远端设备），"
        "这是为鸿蒙「分布式软总线」思想预留的维度，直接支撑任务的跨设备调度；",
        "SSA 的简化模拟：变量每次赋值产生新版本（%x → %x.2），分支汇合处用 φ 指令合并，"
        "为后续优化（常量传播、活跃变量分析）打下基础；",
        "可落地：IR 可翻译为 Mock-C 代码，交由 GCC 编译运行，验证计算结果的正确性。",
    ]),
    ("p", "实现采用 Python 3，新增 5 个模块（ir.py 数据结构、irgen.py 转换、cgen.py 代码生成、"
          "distributed.py 调度模拟、dist_pass.py 跨设备 Pass，约 1100 行）。"
          "实测：样例生成 4 个函数、10 个基本块、33 条 IR 指令；三种调度策略均完成分配并给出负载统计；"
          "配套 40 个单元测试（IR 10 个、转换 12 个、调度 9 个、C 生成 9 个）全部通过。"),

    # ---------------------------------------------------------- 试题
    ("h1", "2 实验上机试题"),
    ("p", "（1）IR 设计与生成：设计一种适合 ArkTS 特性的 IR 格式（参考 LLVM IR，简化实现）；"
          "实现从实验二语义分析后的 AST 到 IR 的转换模块；IR 应能清晰表达基本控制流"
          "（顺序、分支、循环）和基本运算，支持变量、常量和简单函数调用；"
          "考虑引入静态单赋值（SSA）形式的基础概念，如 φ 函数的简单模拟。"),
    ("p", "（2）分布式调度模拟：设计一个简化的分布式环境模型，包含多个模拟的「设备节点」，"
          "每个节点有不同的计算能力（CPU 速度、内存大小）；将生成的 IR 指令序列拆分为可独立调度的"
          "「任务单元」；实现一个简单的调度器，根据预设策略（负载均衡、数据本地化）把任务单元分配到"
          "不同节点上执行；模拟任务执行过程，统计各节点的负载情况和整体执行效率。"),

    # ---------------------------------------------------------- 要求 1、2、3
    ("h1", "3 算法实现"),

    ("h2", "3.1 IR 设计方案与特点"),
    ("p", "IR 采用「模块 → 函数 → 基本块 → 指令」四级结构。指令统一表示为 操作码 + 目标操作数 + 源操作数列表，"
          "操作数是常量字面量、命名变量（%x）或临时变量（%t1）。基本块由一个标签和一条指令序列构成，"
          "块内顺序执行，块间通过 br（条件分支）与 jmp（无条件跳转）连接，因此 if / while / for 都能映射为"
          "「基本块 + 跳转」的图结构。"),
    ("p", "在上述通用结构之上，本 IR 有两处为实验需求所做的扩展：其一，指令与函数都带 device 字段，"
          "构成 DeviceID 维度，使跨设备调度与 RPC 代码生成有据可依；其二，采用变量版本号 + φ 指令"
          "模拟 SSA 形式，支持后续的常量传播、活跃变量分析等经典优化。"),
    ("img", ("图3.2_IR结构示意.png", "图3.2  IR 的四级结构（模块 / 函数 / 基本块 / 指令）示意", 15.5)),
    ("p", "IR 文本格式刻意贴近 LLVM IR：函数头写返回类型与形参，每个基本块以标签开头，"
          "指令缩进两格；函数若被标记为可跨设备执行，会在函数头附加 cross-device 与 device 标注。"),

    ("h2", "3.2 AST 到 IR 的转换规则"),
    ("p", "转换采用「单遍下降 + 按需回填」的方式：遍历 AST，遇到函数 / 方法就开启一个新的 IRFunction，"
          "遇到语句就往下生成指令，遇到表达式就自底向上归约出操作数。核心转换规则如下："),
    ("bullets", [
        "顶层 function → 一个 IRFunction；类/结构体的方法、构造器 → 一个 IRFunction，"
        "名字形如 Person.greet，并把 this 映射为隐含形参 %this；类字段与全局变量 → IRModule.globals；",
        "变量声明 → assign 指令；变量重赋值 → 产生新版本名（SSA），后续引用自动指向最新版本；",
        "二元/一元/逻辑表达式 → 递归求值两个操作数，再生成一条对应操作码的指令，结果放入新临时变量；",
        "if → br 指令 + if.then / if.else / if.end 三个基本块；两条分支各自以 jmp 汇合到 if.end；"
        "汇合块对「在两条路径上版本不同」的变量插入 φ 指令；",
        "while → jmp 到 cond 块，cond 用 br 选择 body 或 end，body 末尾 jmp 回 cond；",
        "for → 依次生成 init、cond、body、update 四块，body 末尾跳到 update，update 再跳回 cond；",
        "函数调用 → 若被调者是方法则把接收者作为第一个实参传入；生成 call 指令，返回值放入临时变量；",
        "return → ret 指令；函数末尾无显式 return 时补一条 ret；",
        "装饰器与 build() 声明式 UI → 不参与计算型 IR，直接跳过。",
    ]),
    ("img", ("图3.1_IR生成流程图.png", "图3.1  AST 到 IR 的转换流程", 12.5)),

    ("h2", "3.3 关键数据结构与核心实现代码"),
    ("p", "（1）IR 的数据结构（ir.py）："),
    ("code", CODE_IR_STRUCT),
    ("p", "（2）函数 / 方法的 IR 生成（irgen.py）："),
    ("code", CODE_GEN_FUNCTION),
    ("p", "（3）SSA 版本命名（irgen.py）——每次赋值产生新版本："),
    ("code", CODE_SSA),
    ("p", "（4）if 语句的分支生成与 φ 函数插入（irgen.py）："),
    ("code", CODE_IF_PHI),
    ("p", "（5）C 代码生成时的 φ 消除（cgen.py）——这是 out-of-SSA 的典型做法："),
    ("code", CODE_CGEN_PHI),

    ("h2", "3.4 分布式调度模拟的模型设计"),
    ("p", "分布式环境用三个数据结构描述："),
    ("bullets", [
        "DeviceNode：模拟的设备节点，字段包括 id、名称、cpu_speed（相对速度）、memory_mb（内存）"
        "与 network_latency_ms（网络延迟）。默认拓扑为「手机(本机) / 平板 / 智慧屏 / 手表」四个节点，"
        "速度分别为 2.0 / 1.5 / 1.2 / 0.7，内存与延迟各不相同；",
        "TaskUnit：可独立调度的任务单元。本实验以「函数」为粒度拆分，计算量 cost = 该函数的 IR 指令条数，"
        "并记录 data_device（数据所在设备，供数据本地化策略使用）与 prefer_device（来自 IR 的 device 标注）；",
        "ScheduleResult：调度结果，包含任务分配表、各设备负载、总工期 makespan 与负载均衡度 balance。",
    ]),
    ("p", "任务拆分之所以选择「函数」粒度，是因为函数天然是「无内部依赖、可整体迁移」的最小单位，"
          "同时也与跨设备 RPC 的调用边界一致；更细的粒度（基本块、指令）会带来大量跨设备通信，"
          "在本实验中反而得不偿失。"),

    ("h2", "3.5 调度策略与模拟流程"),
    ("p", "调度器先把任务按计算量降序排序（长任务优先，有利于降低 makespan），再按策略选择目标设备："),
    ("bullets", [
        "轮询（round_robin）：依次把任务分给各设备，实现最简单，不考虑负载差异；",
        "最短队列优先（least_loaded）：每次把任务分给当前累计耗时最小的设备，属于贪心负载均衡；",
        "数据本地化（data_locality）：优先把任务放在数据所在设备上，以减少跨设备数据搬运；"
        "若该设备不在拓扑中则退化为最短队列优先。",
    ]),
    ("p", "模拟执行时，每个设备串行执行分配给它的任务，耗时累加 cost / cpu_speed；"
          "若任务的 data_device 与目标设备不一致，再额外叠加该设备的网络延迟。"
          "全部任务模拟完成后统计：各设备负载、总工期 makespan = max(负载)、"
          "负载均衡度 balance = 1 − (max − min) / makespan（越接近 1 越均衡）。"),
    ("img", ("图3.3_调度模拟流程.png", "图3.3  分布式调度模拟流程", 13.0)),
    ("p", "（6）调度器核心实现（distributed.py）："),
    ("code", CODE_SCHEDULE),

    ("h2", "3.6 实现结果：IR 示例与调度数据"),
    ("img", ("图3.4_IR生成示例.png", "图3.4  samples/ir_demo.ets 生成的 IR（classify 函数，含 SSA 与 φ）", 15.5)),
    ("p", "图 3.4 是样例生成的 IR 片段。可以清楚看到 SSA 的作用：result 在初始、then 分支、else 分支"
          "分别取到 %result、%result.2、%result.3 三个版本，汇合块用 φ 指令选出正确的那个。"
          "整个模块共 4 个函数、10 个基本块、33 条 IR 指令。"),
    ("p", "IR 文本实况："),
    ("code", OUT_IR),
    ("p", "分布式 Pass 的纯度分析结果与三种策略的调度数据："),
    ("code", OUT_SCHED),
    ("p", "其中 square / sumTo / classify / demo 四个函数都被判定为「纯计算、无副作用」，"
          "因而被标记为可跨设备执行并轮转到远端设备；模块里没有写字段、写数组或 IO 调用的函数。"),
    ("img", ("图3.5_调度结果对比.png", "图3.5  三种调度策略的 makespan 与负载均衡度对比", 15.5)),
    ("p", "为可跨设备函数生成的 RPC 桩（Stub / Skeleton）："),
    ("code", OUT_RPC),
    ("p", "Skeleton 部署在远端设备上真正执行函数，Stub 部署在本机侧负责打包参数、"
          "经「软总线」（本实验用 ark_softbus_send 模拟）发送并取回结果。"
          "生成的 Mock-C 代码可直接用 GCC 编译运行："),
    ("code", "gcc out/ir_demo.c -o out/ir_demo.exe -lm\nout/ir_demo.exe\n# 输出 156  (= 100 + 55 + 1)"),

    # ---------------------------------------------------------- 要求 4
    ("h1", "4 测试"),
    ("p", "针对 IR 生成、分布式调度与 Mock-C 代码生成分别设计测试用例，覆盖正常值、边界值与错误值。"),
    ("table", (TABLE_IR, "表3.1  试题1（IR 生成）测试用例")),
    ("table", (TABLE_SCHED, "表3.2  试题2（分布式调度模拟）测试用例")),
    ("table", (TABLE_CGEN, "表3.3  Mock-C 代码生成测试用例")),
    ("p", "以上用例均已实现为自动化单元测试（tests/test_ir.py、test_irgen.py、test_distributed.py、test_cgen.py），"
          "执行 python -m unittest discover -s tests 可一次性运行全部 104 个用例（含实验一、二的 64 个），实测全部通过。"),

    # ---------------------------------------------------------- 难点
    ("h1", "5 难点和解决办法"),
    ("h3", "难点 1：SSA 版本命名与「引用随版本走」"),
    ("p", "问题：变量一旦被重新赋值就必须产生新版本，而后续所有对该变量的引用又必须指向最新版本，"
          "否则 IR 语义就错了；只改赋值点而不改引用点，生成的代码会读到陈旧的值。"),
    ("p", "解决办法：维护一张「源变量名 → 当前 IR 名」的映射 env。每次赋值由 _define 递增版本号"
          "（%x → %x.2 → %x.3）并刷新映射；所有读取统一走 _ref，从映射中取当前版本。"
          "进入分支前对映射做快照，两条路径各用独立副本，从而互不干扰。"),
    ("h3", "难点 2：分支汇合处的 φ 插入时机与入边选择"),
    ("p", "问题：if 的两条分支可能给同一变量赋了不同版本，汇合块必须用一条指令选出「来时所走路径」上的值；"
          "但 φ 的结果取决于控制流从哪条边进入，静态无法确定。"),
    ("p", "解决办法：φ 的每个入边都记录 (值, 前驱块标签) 二元组，由后端的跳转指令负责按边选择；"
          "并且只对「两条路径上版本确实不同」的变量插入 φ，避免生成冗余指令。"),
    ("h3", "难点 3：C 代码没有 φ，如何保持语义"),
    ("p", "问题：C 是命令式语言，不存在 φ 指令，直接翻译会丢掉分支汇合的语义。"),
    ("p", "解决办法：采用 out-of-SSA——把 φ 的赋值下沉到前驱块：在 jmp / br 跳往汇合块之前先执行"
          "「φ 目标 = 该边对应的实参」，φ 指令本身不生成任何代码。这与真实编译器消除 SSA 的做法一致。"),
    ("h3", "难点 4：循环的 IR 结构（回边与初始跳转）"),
    ("p", "问题：while / for 不是顺序结构，且 for 的 update 位于 body 之后、cond 之前，"
          "处理不当会生成块顺序混乱、出口不唯一的 IR。"),
    ("p", "解决办法：统一采用「入口先 jmp 到 cond」的模式——cond 用 br 分出 body 与 end；"
          "while 的 body 末尾跳回 cond，for 的 body 末尾跳到 update、update 再跳回 cond。"
          "这样每个基本块只有一个出口，既便于静态排序，也便于后端翻译成标签 + goto。"),
    ("h3", "难点 5：循环中变量的版本处理"),
    ("p", "问题：循环体会执行多次，循环出口处变量的取值既可能是初始值，也可能是某次迭代后的值，"
          "严格 SSA 需要在循环头插入 φ 才能在出口处正确取值。"),
    ("p", "解决办法：本实验做了简化——保留循环体内产生的新版本（不做循环头 φ），保证生成的计算结果正确；"
          "同时在报告中明确指出这是与「完整 SSA」的差距：完整实现需要计算支配边界并按 Cytron 算法"
          "插入 φ 再做变量重命名。"),
    ("h3", "难点 6：任务粒度与调度指标的定义"),
    ("p", "问题：任务拆得太细会引入大量跨设备通信开销，太粗又无法做负载均衡；"
          "「负载」「工期」若定义不当，还会得出错误结论。"),
    ("p", "解决办法：选择「函数」粒度——它与跨设备 RPC 的调用边界一致，且天然无内部依赖；"
          "用函数的 IR 指令条数度量计算量，用 cpu_speed 做归一化，跨设备时叠加网络延迟；"
          "总工期取 makespan（最大负载），均衡度取 1 - (max - min) / makespan。"),

    # ---------------------------------------------------------- 要求 5
    ("h1", "6 调度策略优劣分析与鸿蒙应用场景"),
    ("p", "结合图 3.5 的实测数据，三种策略的对比如下："),
    ("bullets", [
        "轮询：实现最简单、无状态、开销恒定，但在本实验中 makespan=8.34；"
        "由于本实验任务数恰好等于设备数且已按耗时降序排列，它恰好把最重任务分给了最快的设备，"
        "表现与最短队列优先相同——这是数据规模小带来的巧合，任务数一变其表现就会明显劣化；",
        "最短队列优先：贪心地把每个任务交给当前最轻的设备，makespan=8.34、balance=0.344，"
        "在本组数据上表现最好；缺点是只依据「已有负载」决策，不考虑数据位置，"
        "对数据密集型任务可能引入额外的跨设备搬运；",
        "数据本地化：强制把任务放在数据所在设备，balance=0.000、makespan=14.29，本组数据中最差——"
        "因为最慢的「手表」(speed 0.7) 恰好持有最重的任务，负载被完全压到它身上，形成了「木桶效应」。"
        "这说明数据本地化只有在「算力分布均匀」时才划算，否则必须引入权重折中。",
    ]),
    ("p", "结论：不存在放之四海皆准的最优策略。实际系统通常采用混合策略——"
          "先按数据本地化尝试，若目标设备负载明显偏高（或算力明显偏低）则退化为最短队列优先，"
          "这正是「数据本地化 + 负载均衡」的加权折中思路，也是本实验可继续改进的方向之一。"),
    ("p", "在真实鸿蒙系统中的应用场景：鸿蒙的分布式软总线为跨设备调用提供了传输与发现能力，"
          "上层则负责决定「哪个任务交给哪台设备」。典型场景包括："
          "① 手机拍摄、智慧屏显示——把图像处理任务下沉到算力更强的设备；"
          "② 手表由于算力弱、电量低，只负责采集，把计算交给手机或平板；"
          "③ 多设备协同渲染/推理时，按数据位置就近调度以减少传输。"
          "本实验的 DeviceID 维度与 RPC Stub/Skeleton 正是这些机制的最小化模拟。"),

    # ---------------------------------------------------------- 要求 6
    ("h1", "7 实验总结与改进方向"),
    ("p", "本实验完成了从 AST 到三地址码 IR 的完整转换，并在 IR 上模拟了分布式任务调度。"
          "收获主要有三点：一是切身理解了 IR 作为「编译器中端公共语言」的价值——"
          "正是因为 IR 与源语言、目标机器都解耦，优化与调度才能独立于前后端实现；"
          "二是通过手写 SSA 版本命名与 φ 插入，真正看清了「变量在控制流汇合处有两个可能取值」"
          "这一问题的本质，以及 out-of-SSA 时为什么必须在每条入边上插入赋值；"
          "三是体会了分布式调度的核心矛盾——算力、数据位置与通信开销三者之间的权衡。"),
    ("h3", "IR 层面的改进方向"),
    ("bullets", [
        "常量折叠与常量传播：在现有 SSA 形式下，把 %t = mul 3, 4 直接折叠为 12，"
        "并把常量代入后续使用，可显著减少指令数（这正是实验四要实现的优化）；",
        "死代码消除：结合活跃变量分析，删除结果从未被使用且无副作用的指令；",
        "公共子表达式消除：在 SSA 形式下，值编号（value numbering）可以天然识别出 a+b 与 b+a 的等价；",
        "循环优化：循环不变量外提、归纳变量强度削弱（把 i*4 换成指针自增）等；",
        "真实 SSA 构造：目前只在 if 汇合处插入 φ，循环头缺少 φ；完整的 SSA 构造需要计算"
        "支配边界并插入 φ、再做变量重命名，可用经典的 Cytron 算法实现。",
    ]),
    ("h3", "调度算法层面的改进方向"),
    ("bullets", [
        "引入数据依赖图：当前以「函数」为粒度，忽略了函数间的调用与数据依赖；"
        "若把 IR 的调用图进入调度，就要保证依赖任务在同一设备或按序执行，甚至需要任务迁移；",
        "考虑通信开销与带宽：目前只把网络延迟作为固定惩罚，实际应根据传输数据量动态估算；",
        "动态反馈调度：按设备的实时负载与剩余电量动态调整，而非一次性静态分配；",
        "容错与重试：远端设备掉线时需要把任务重新调度回本机，可引入副本与心跳机制；",
        "多目标优化：把 makespan、能耗、内存峰值纳入统一目标函数，"
        "用启发式（如列表调度、遗传算法）求解，而不是单一贪心策略。",
    ]),

    # ---------------------------------------------------------- 思考题
    ("h1", "8 思考题"),
    ("h3", "思考题 1：SSA 形式为何能简化编译器的优化过程？本实验实现 SSA 面临哪些挑战？"),
    ("p", "SSA 之所以能简化优化，是因为它把「一个变量可能被多处、多次定义」变成了「每个变量只有一个定义点」，"
          "def-use（定义-使用）关系因此显式化：每个使用点都能直接追溯到唯一的定义点。"
          "于是常量传播、常量折叠、值编号（公共子表达式消除）、死代码消除、活跃变量分析等"
          "都退化为沿 def-use 链的简单遍历，不再需要迭代求解到达定值（reaching definitions）这类数据流方程。"),
    ("p", "在本实验中实现 SSA 面临的挑战主要有：① φ 函数的语义本身依赖控制流——取值取决于"
          "「从哪条边进入该基本块」，因此必须把前驱块信息一并记录才能在后端正确还原；"
          "② φ 的插入位置并非随意决定，理论上要计算支配边界（dominance frontier），"
          "本实验只在简单 if 汇合处插入，未实现完整的 Cytron 算法；"
          "③ 循环头同样需要 φ，本实验做了简化；④ φ 必须在后端消除（out-of-SSA），"
          "把赋值下沉到各条入边时还要避免丢失复制与交换次序问题；"
          "⑤ 变量重命名要贯穿所有使用点，版本映射若在某条分支上漏改，就会生成语义错误的 IR。"),
    ("h3", "思考题 2：鸿蒙的「分布式软总线」为分布式任务调度提供了哪些底层支持？"),
    ("p", "分布式软总线相当于为多设备提供了一条「虚拟的统一总线」，它在底层解决了三件事："
          "① 设备发现与组网——自动发现附近设备并建立可信连接，调度器无需关心设备如何被找到；"
          "② 统一传输——屏蔽 Wi-Fi、蓝牙、USB 等物理链路差异，提供统一的通道与多路复用能力；"
          "③ 远程调用与数据同步——把跨设备调用封装成接近本地调用的形式，并提供跨设备的数据访问与同步。"),
    ("p", "落到调度上，这些能力意味着：调度器只需在上层做「任务 → 设备」的分配决策，"
          "底层连通性、传输、安全与权限由软总线保障；同时因为数据可以跨设备访问，"
          "「数据本地化」才成为一个可选的优化目标而非硬约束。本实验中的 DeviceID 维度、"
          "ArkRpcEnvelope 与 ark_softbus_send 正是这套机制的最小化模拟。"),
    ("h3", "思考题 3：除计算资源外，分布式调度还需要考虑哪些因素？"),
    ("bullets", [
        "数据依赖：任务之间存在数据或控制依赖时，必须保证执行顺序或落到同一设备，否则结果错误；",
        "通信开销：跨设备传输的数据量与带宽决定「本地化」是否真的划算，需要与算力收益做权衡；",
        "容错性：远端设备可能掉线、超时或执行失败，需要重试、副本或回退到本机；",
        "能耗：移动设备的电量是硬约束，把重任务丢给手表可能导致电量迅速耗尽；",
        "异构能力与内存：不同设备内存容量不同，有些还带 NPU 等专用单元，适合不同类型的任务；",
        "实时性与优先级：时延敏感任务应就近执行，不能被长任务拖住；",
        "状态迁移成本：任务在设备间迁移时，搬运其运行状态（激活值、中间数据）本身也是开销。",
    ]),
]