"""生成《编译技术》实验一实验报告。

输出：
    report/实验一报告.docx   可直接编辑 / 提交
    report/实验一报告.md     便于预览或复制

内容按课程模板的 5 个小节组织：1 内容简介 / 2 实验上机试题 /
3 算法实现（3.1 算法流程设计、3.2 实现结果）/ 4 测试 / 5 难点和解决办法。
"""

from __future__ import annotations

import pathlib
import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import figures  # noqa: E402

FIGDIR = ROOT / "report" / "figures"
OUT_DOCX = ROOT / "report" / "实验一报告.docx"
OUT_MD = ROOT / "report" / "实验一报告.md"
CENTER = WD_ALIGN_PARAGRAPH.CENTER

# ============================================================ 报告正文内容
TABLE_LEX = (
    ["用例编号", "测试项", "测试步骤", "预期结果", "测试结果"],
    [
        ["1", "输入合法值",
         "输入 let count = 0; ，调用词法分析器",
         "依次得到 LET、IDENTIFIER、ASSIGN、NUMBER、SEMICOLON、EOF 共 6 个 Token，无错误", "通过"],
        ["2", "边界值：空输入",
         "输入空字符串",
         "仅产生 1 个 EOF Token，错误数为 0", "通过"],
        ["3", "边界值：多形式数字字面量",
         "输入 0 42 3.14 1e3 0xFF 0b1010 1_000",
         "识别出 7 个 NUMBER，词素原文与输入完全一致", "通过"],
        ["4", "边界值：多字符运算符最长匹配",
         "输入 === !== >>> => ?.",
         "依次识别为 STRICT_EQ、STRICT_NEQ、USHR、ARROW、OPTIONAL_CHAIN，未出现拆分错误", "通过"],
        ["5", "等价类：注释",
         "分别输入 let x=1; // 行注释 与 /* 块注释 */ const y=2;",
         "注释被完整跳过，不产生 Token 且不报错", "通过"],
        ["6", "边界值：行列定位",
         "输入两行代码 let x; 换行 两个空格 + let y;",
         "第二个标识符 y 的位置记录为 第 2 行第 7 列", "通过"],
        ["7", "输入错误值：未闭合字符串",
         "输入 let s = 'abc",
         "报错「未闭合的字符串字面量」，位置 1:9，且扫描继续不崩溃", "通过"],
        ["8", "输入错误值：非法字符",
         "输入 let a = #; let b = 2;",
         "报错「非法字符 '#'」，且仍能识别出后续 2 个 let 关键字", "通过"],
    ],
    [1.3, 2.5, 5.0, 5.4, 1.4],
)

TABLE_PARSE = (
    ["用例编号", "测试项", "测试步骤", "预期结果", "测试结果"],
    [
        ["1", "输入合法值：变量声明",
         "输入 let x: number = 1;",
         "生成 VariableDeclaration，含 TypeAnnotation(number) 与 Literal(1)", "通过"],
        ["2", "输入合法值：鸿蒙组件",
         "输入 @Entry @Component struct Page { @State n: number = 0; build() { Text('hi') } }",
         "生成 ClassDeclaration(kind=struct)，含 2 个 Decorator、FieldDeclaration、MethodDeclaration，build() 中 Text('hi') 被识别为 UiContainer 的子语句", "通过"],
        ["3", "边界值：if 无 else 分支",
         "输入 if (a) { b = 1; }",
         "生成 IfStatement，且 alternate 字段为空", "通过"],
        ["4", "边界值：运算符优先级",
         "输入 let r = 1 + 2 * 3;",
         "乘法节点嵌套在加法节点之内（先算 * 再算 +）", "通过"],
        ["5", "等价类：箭头函数两种写法",
         "分别输入 (a: number) => a + 1 与 x => x * 2",
         "均生成 ArrowFunctionExpression，表达式体与块体均正确", "通过"],
        ["6", "输入错误值：缺少分号",
         "输入 let x = 1 换行 let y = 2;",
         "报错「缺少分号 ';'」，且错误恢复后仍解析出第二条变量声明", "通过"],
        ["7", "输入错误值：括号不匹配",
         "输入 if (a) { b = 1;（缺少右花括号）",
         "报错「期望 '}'，但遇到 文件结尾」", "通过"],
        ["8", "输入错误值：缺少表达式",
         "输入 let x = ;",
         "报语法错误并定位到分号所在位置", "通过"],
    ],
    [1.3, 2.5, 5.0, 5.4, 1.4],
)

CONTENT = [
    ("title", "实验一  鸿蒙 ArkTS 词法分析与语法分析器设计"),

    ("h1", "1 内容简介"),
    ("p", "本实验完成了一个面向鸿蒙应用开发语言 ArkTS 的编译器前端，覆盖词法分析与语法分析两个阶段。"
          "词法阶段定义了 ArkTS 子集的词法规则并实现词法分析器，把源代码字符串切分为 Token 序列；"
          "语法阶段为 ArkTS 核心子集定义了上下文无关文法，并采用递归下降法实现语法分析器，"
          "把 Token 序列构造为抽象语法树（AST）。在此基础上实现了 AST 的遍历、S-表达式打印、JSON 序列化导出"
          "以及浏览器中的树形可视化，并针对非法字符、未闭合字符串、缺少分号、括号不匹配等错误实现了检测、定位与恢复。"),
    ("p", "与标准 TypeScript 相比，本实验重点处理了 ArkTS 的私有语法结构："),
    ("bullets", [
        "装饰器：@Entry、@Component、@State、@Prop、@Builder 等；",
        "组件声明：struct 组件与 class、interface 并存；",
        "声明式 UI：build() 方法中形如 Column() { Text('hi') } 的「组件调用 + 尾随块」结构。",
    ]),
    ("p", "实现采用 Python 3 编写，共 8 个源码模块（约 1200 行），配套 30 个单元测试；"
          "另提供命令行入口 main.py 与一键验证脚本 build.py。实测 3 个合法样例（hello.ets、counter.ets、"
          "algorithms.ets）解析零错误，1 个错误样例可一次性报出 6 条诊断，30 个单元测试全部通过。"),

    ("h1", "2 实验上机试题"),
    ("p", "（1）词法分析："),
    ("bullets", [
        "定义 ArkTS 语言的词法规则，包括关键字（let、const、if、for、class、struct 等）、标识符、"
        "数字字面量、字符串字面量、注释、运算符及分隔符；",
        "实现词法分析器，输入为 ArkTS 源代码字符串，输出为对应的 Token 序列；",
        "处理词法错误，如非法字符、未闭合的字符串等。",
    ]),
    ("p", "（2）语法分析："),
    ("bullets", [
        "选取 ArkTS 的一个核心子集（变量声明、赋值语句、if-else 语句、while/for 循环、函数定义与调用、"
        "类与结构体及装饰器、声明式 UI），定义其上下文无关文法；",
        "基于所选文法实现递归下降分析器；",
        "将输入的 Token 序列解析为抽象语法树（AST），并实现 AST 的遍历与打印功能；",
        "处理语法错误，如括号不匹配、缺少分号等。",
    ]),

    ("h1", "3 算法实现"),
    ("h2", "3.1 算法流程设计"),
    ("img", ("图1.1_词法分析流程图.png", "图1.1  词法分析器算法流程图", 12.0)),
    ("p", "词法分析器采用单遍扫描（one-pass）。进入循环后先跳过空白与注释，再依据当前字符的类别分派到对应的读取子过程："
          "数字按进制前缀 / 小数 / 指数形式识别；字符串与模板串处理转义序列并判定是否闭合；"
          "标识符读取完成后查关键字表决定其是关键字还是普通标识符；运算符则把运算符表按长度降序排列后逐项做前缀匹配，"
          "以保证最长匹配（例如 === 优先于 ==，>>> 优先于 >>）。每识别出一个词素即生成 Token 并记录行列号；"
          "识别失败时并不终止，而是记录一条诊断后跳过该字符，从而保证一次扫描能够报告多个错误。"),
    ("img", ("图1.2_语法分析流程图.png", "图1.2  语法分析器算法流程图", 12.0)),
    ("p", "语法分析器采用递归下降法，为文法的每个非终结符编写一个解析函数，并按运算符优先级分层："
          "赋值 → 条件 → 逻辑 → 位运算 → 相等 → 关系 → 移位 → 加减 → 乘除 → 一元 → 后缀 → 原子，逐层下降，"
          "从而无需回溯即可确定唯一分析路径。解析一条语句成功时构造对应的 AST 节点；失败时抛出携带位置信息的诊断，"
          "由语句层的「恐慌模式」捕获，随后按同步集跳过若干 Token，恢复到下一条语句的起点继续解析，"
          "因此一次编译能够报告多个语法错误。"),

    ("h2", "3.2 实现结果"),
    ("img", ("图1.3_hello的AST.png", "图1.3  samples/hello.ets 解析得到的抽象语法树（缩进打印）", 15.5)),
    ("p", "图 1.3 为 samples/hello.ets 的 AST 打印结果。可以看到：@Entry、@Component 装饰器被解析为 Decorator 节点并挂载到"
          "ClassDeclaration(kind=struct) 上；@State 修饰的字段成为带装饰器的 FieldDeclaration；"
          "build() 方法被解析为 MethodDeclaration，其方法体中的 Column() { ... } 被识别为 UiContainer，"
          "子组件 Text、Button 则作为其 children，Text 后面的 .fontSize(24) 等链式调用被解析为 MemberExpression 与 CallExpression 的组合。"),
    ("img", ("图1.4_hello的词法输出.png", "图1.4  samples/hello.ets 的词法分析输出（前若干 Token）", 15.5)),
    ("p", "图 1.4 为同一份源码的词法分析输出，共 64 个 Token、0 个词法错误，"
          "可见 @、标识符、关键字、字符串、运算符等词素均被正确切分并标注了行列位置。"),
    ("p", "除终端打印外，程序还支持把 AST 导出为 JSON 并生成单文件 HTML 可视化页面（不依赖任何外部库，可离线使用），"
          "在浏览器中可折叠与搜索节点。完整产物见 out/hello.html、out/counter.html、out/algorithms.html。"),

    ("h1", "4 测试"),
    ("p", "针对词法与语法两个试题分别设计测试用例，覆盖正常值、边界值与错误值。"),
    ("table", (TABLE_LEX, "表1.1  试题1（词法分析）测试用例")),
    ("table", (TABLE_PARSE, "表1.2  试题2（语法分析）测试用例")),
    ("p", "说明：以上用例均已在 tests/test_lexer.py 与 tests/test_parser.py 中实现为自动化单元测试，"
          "执行 python -m unittest discover -s tests 可一次性运行全部 30 个用例，实测结果全部通过。"
          "错误用例不仅校验「报错」，还校验「报错后能继续解析后续代码」，即错误恢复能力。"),

    ("h1", "5 难点和解决办法"),
    ("h3", "难点 1：ArkTS 相对 TypeScript 的私有语法（装饰器 / struct / 声明式 UI）"),
    ("p", "问题：Column() { Text('hi') } 这种「函数调用 + 尾随代码块」并不是标准表达式语句，"
          "按普通调用文法解析会在遇到 { 时报「意外的 '{'」。"),
    ("p", "解决办法：在表达式语句的解析中加入前瞻——当解析完一个 CallExpression 后紧随 { 时，"
          "就把它升级为专门的 UiContainer 节点，把尾随块解析为 children 语句列表。"
          "这样声明式 UI 的嵌套结构（Column 套 Row、Row 套 Text）可以被递归、准确地表达。"),
    ("h3", "难点 2：错误恢复不能吞掉后续合法语句"),
    ("p", "问题：最初采用「跳到下一个分号」的同步策略，结果在 let x = 1（缺分号）之后，"
          "会把下一条合法语句 let y = 2; 整条吃掉，导致漏报。"),
    ("p", "解决办法：把同步集细分为三类——语句起始符（let/const/if/while/for/struct/@/…）：立即停止且不消费，交回上层继续解析；"
          "终止符（分号、右花括号）：消费后停止；其它 Token：跳过。同时保证每条恢复路径都至少前进一个 Token，避免死循环。"),
    ("h3", "难点 3：声明式 UI 组件不写分号 与「缺少分号」检测的冲突"),
    ("p", "问题：在 build() 中组件语句按 ArkTS 习惯不写分号，但其它位置缺分号必须报错，两者用同一套规则会互相干扰。"),
    ("p", "解决办法：引入 ui_depth 上下文标志，仅在 build() 与 @Builder 方法体内才容忍组件调用语句省略分号；"
          "其它位置缺少分号仍照常报错，从而既贴合鸿蒙代码风格，又保留了「缺少分号」的错误检测能力。"),
    ("h3", "难点 4：运算符的最长匹配"),
    ("p", "问题：若按固定顺序匹配运算符，=== 会被拆成 == 与 =，>>> 会被拆成 >> 与 >，导致 Token 序列错误。"),
    ("p", "解决办法：将所有运算符按长度降序排序后逐项做前缀匹配，命中即消费对应长度的字符。"
          "该策略同时自然地覆盖了 =>、?.、...、++ 等多字符运算符。"),
    ("h3", "算法具体应用场景"),
    ("bullets", [
        "集成开发环境：语法高亮、代码补全、跳转与重构均直接依赖词法与语法分析结果；",
        "静态检查工具：ARKTS 的强类型静态检查需要先得到正确的 AST，本实验的 AST 是实验二语义分析的基础；",
        "方舟编译器前端：其编译流程为「词法 → 语法 → 语义 → IR → 机器码」，本实验完成的正是前两个阶段；",
        "后续实验衔接：实验二在本实验的 AST 上做符号表与类型检查，实验三在此基础上生成中间表示（IR）。",
    ]),

    ("h1", "6 思考题"),
    ("h3", "思考题 1：ArkTS 相较于标准 TypeScript 有哪些主要语法差异？对词法/语法分析有何影响？"),
    ("p", "ArkTS 并不是一门全新的语言，它以 TypeScript 为语法基础，通过「做减法 + 加约束」来强化开发期的静态检查，"
          "差异可以归纳为两类。"),
    ("p", "（一）语义与约束层面的差异：禁用 any、unknown 等动态类型；禁止运行期改变对象布局（如用 delete 删除对象属性）；"
          "不支持 eval、with、arguments、Function.apply/call、Symbol 等会突破静态分析能力的动态特性；"
          "类与结构体的字段必须显式声明类型并初始化；不接受 TypeScript 的结构化类型（Structural Typing）带来的隐式兼容，"
          "要求显式的类型标注。这类差异几乎不改变词法单元（关键字集合基本沿用 TS），"
          "但显著影响语法分析的「宽严尺度」与后续语义检查——文法可以、也应该更严格，无需为动态写法预留产生式。"),
    ("p", "（二）语法结构层面的差异：装饰器（@Entry、@Component、@State 等）被大量使用；新增 struct 组件声明；"
          "具有声明式 UI 语法（build() 中形如 Column() { Text('hi') } 的「组件调用 + 尾随块」），这在标准 TypeScript 中并不存在。"),
    ("p", "对词法分析的具体影响：① @ 必须作为合法词法单元（AT）而非非法字符，并与标识符组合成装饰器；"
          "② struct 需要提升为关键字；③ 组件语句之间常常不写分号，且换行不构成确切的语句边界，"
          "仅凭词法层无法判断，必须交由语法层前瞻处理；④ 模板字符串 ${} 内部可能嵌套任意表达式，需按括号计数读取。"),
    ("p", "对语法分析的具体影响：① 文法需要支持「装饰器列表 + 声明」的复合结构；"
          "② struct 与 class 的成员文法可以复用同一套产生式，只在语义阶段区分约束；"
          "③ 声明式 UI 的「调用 + 尾随块」需要专门的非终结符（本实验的 UiContainer），且该上下文中分号可选；"
          "④ 由于动态特性被禁用，分析器不必为 TS 的极端写法保留宽松分支。"),

    ("h3", "思考题 2：递归下降分析与 LR 分析各有什么优缺点？为何现代编译器前端倾向递归下降？"),
    ("p", "递归下降分析（自顶向下、手写）：优点是「代码即文法」，直观可读、易于调试；"
          "错误信息可以非常精准，能够给出「期望 X，但遇到 Y」并定位到行列；便于实现错误恢复（恐慌模式 + 同步集），"
          "从而一次编译报告多个错误；能够自然地进行语法制导翻译、边解析边构造 AST；"
          "对上下文相关的语法可以显式控制（本实验的「UI 块内免分号」就是靠 ui_depth 实现的）。"
          "缺点是不能直接处理左递归，文法必须改写；表达能力受限于 LL 类文法，复杂处需要多 token 前瞻甚至回溯；"
          "运算符优先级需要分层（本实验分了 12 层）或采用优先级爬升技巧；文法改动必须同步修改代码。"),
    ("p", "LR 分析（自底向上、由 Yacc/Bison 生成）：优点是解析能力更强，可处理左递归与更广的文法类；"
          "表驱动、效率高且稳定；文法以声明式文件维护，改文法不必改代码。"
          "缺点是错误信息对使用者不友好（往往只报 syntax error 与状态号）；错误恢复与容错解析难以实现；"
          "生成的语法分析表是黑盒，调试困难；上下文相关的语法需要「lexer hack」在词法层打补丁；"
          "构造 AST 还需额外编写语义动作代码。"),
    ("p", "现代编译器前端之所以倾向递归下降，主要有五点原因：① 诊断质量优先——Clang、Go、Rust、TypeScript 等"
          "都把「错误信息友好、能给出修复建议」当作核心体验，这在手写递归下降中最容易做到；"
          "② 编辑器场景需要增量与容错解析——IDE 必须在代码不完整时也能解析，手写递归下降可自由选择恢复点，"
          "而 LR 面向批处理、一旦出错难以继续；③ 大量语言存在上下文相关语法（JavaScript 的自动分号插入、TS 的 JSX、"
          "ArkTS 的装饰器与声明式 UI），LR 需要 lexer hack，而递归下降可用显式上下文标志解决；"
          "④ 性能不再是瓶颈——手写递归下降速度足够、内存占用小；⑤ 工程可维护性好——代码即文法，团队协作与代码评审更直观。"),
    ("p", "结论：若追求「严格按标准定义解析 + 自动生成」，LR/GLR 仍然适用；"
          "但对面向 IDE 的语言前端而言，诊断与容错更为关键，因此递归下降成为主流。本实验选择递归下降，"
          "正是看中它能清楚地定位并恢复错误，便于实验二在含错误的代码上继续做语义分析。"),

    ("h3", "思考题 3：如何扩展本实验的语法分析器以支持 ArkTS 的装饰器语法？"),
    ("p", "本实验的语法分析器实际上已经支持了装饰器语法。已实现的部分包括："
          "① 词法层把 @ 识别为独立 Token（TokenType.AT），因此 @Entry 被切分为 AT + IDENTIFIER，而不会被当成非法字符；"
          "② 语法层的 _decorators() 用循环解析「@ + 标识符 + 可选参数列表」，生成 Decorator 节点，"
          "并在语句层（修饰 struct/class/interface）与类成员层（修饰字段与方法）两处调用；"
          "③ AST 层为 ClassDeclaration、MethodDeclaration、FieldDeclaration 都提供了 decorators 列表字段；"
          "④ @ 后缺少标识符、装饰器未修饰合法目标时会给出明确诊断。"),
    ("p", "可进一步扩展的方向：① 装饰器表达式化——目前装饰器名只接受单个标识符，"
          "标准 TS 允许 @decorators[0]、@foo() 这类表达式，可把 _decorators() 中的 _expect(IDENTIFIER) 替换为 _postfix()，"
          "从而接受成员访问、下标与调用等任意表达式；② 扩大装饰器可修饰的目标范围——"
          "当前支持 struct/class/interface 与方法/字段，可扩展到独立函数（@Builder function foo() {}）与参数装饰器；"
          "③ 装饰器参数的类型化——@Watch('onChange') 这类参数在语法层只是普通实参列表，"
          "可在实验二的语义阶段按装饰器名校验参数个数与类型，并在 Decorator 节点上增加 resolvedType 等字段；"
          "④ 更精准的约束诊断——把「装饰器可以出现在哪些位置」的规则从语法层的兜底报错上移为语义层规则检查"
          "（例如 @State 只能在 @Entry 组件内），使语法与语义职责更清晰；"
          "⑤ 换行与续行处理——ArkTS 允许装饰器与方法之间换行，目前依靠 Token 流的自然分隔即可正确解析；"
          "若引入自动分号插入语义，则需像 ui_depth 一样增加上下文标志来区分换行是否构成语句边界。"),
    ("p", "小结：装饰器的扩展点集中在「装饰器本身的表达式化」与「装饰器可修饰的目标范围」两处，"
          "二者都不需要改动词法层（因为 @ 已经是独立 Token），属于典型的语法层增量扩展。"),
]


# ============================================================ docx 渲染
def _font(run, name="宋体", size=12, bold=False):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    for attr in ("w:eastAsia", "w:ascii", "w:hAnsi"):
        rfonts.set(qn(attr), name)


def para(doc, text, size=12, bold=False, font="宋体", align=None,
         space_after=6, line_spacing=1.5, first_indent=False, left_indent=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    _font(run, font, size, bold)
    if align is not None:
        p.alignment = align
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.line_spacing = line_spacing
    if first_indent:
        pf.first_line_indent = Pt(size * 2)
    if left_indent is not None:
        pf.left_indent = Pt(left_indent)
    return p


def add_picture(doc, filename, caption, width_cm):
    doc.add_picture(str(FIGDIR / filename), width=Cm(width_cm))
    doc.paragraphs[-1].alignment = CENTER
    para(doc, caption, size=10.5, align=CENTER, space_after=10)


def add_table(doc, header, rows, widths, caption):
    para(doc, caption, size=10.5, bold=True, align=CENTER, space_after=4)
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    for i, text in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(text)
        _font(run, "黑体", 10.5, True)
        cell.paragraphs[0].alignment = CENTER
    for row in rows:
        cells = table.add_row().cells
        for i, text in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            run = p.add_run(text)
            _font(run, "宋体", 10)
            p.paragraph_format.line_spacing = 1.25
    for r in table.rows:
        for cell, w in zip(r.cells, widths):
            cell.width = Cm(w)
    para(doc, "", space_after=8)


def render_docx() -> pathlib.Path:
    doc = Document()
    for section in doc.sections:
        section.top_margin = Cm(2.4)
        section.bottom_margin = Cm(2.4)
        section.left_margin = Cm(2.8)
        section.right_margin = Cm(2.8)

    for kind, payload in CONTENT:
        if kind == "title":
            para(doc, payload, size=18, bold=True, font="黑体", align=CENTER, space_after=16)
        elif kind == "h1":
            para(doc, payload, size=14, bold=True, font="黑体", space_after=8)
        elif kind == "h2":
            para(doc, payload, size=12.5, bold=True, font="黑体", space_after=6)
        elif kind == "h3":
            para(doc, payload, size=12, bold=True, font="黑体", space_after=6)
        elif kind == "p":
            para(doc, payload, first_indent=True)
        elif kind == "bullets":
            for item in payload:
                para(doc, "· " + item, left_indent=24, space_after=4)
        elif kind == "img":
            filename, caption, width_cm = payload
            add_picture(doc, filename, caption, width_cm)
        elif kind == "table":
            (header, rows, widths), caption = payload
            add_table(doc, header, rows, widths, caption)

    OUT_DOCX.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT_DOCX))
    return OUT_DOCX


# ============================================================ markdown 渲染
def render_md() -> pathlib.Path:
    lines: list[str] = []
    for kind, payload in CONTENT:
        if kind == "title":
            lines += [f"# {payload}", ""]
        elif kind == "h1":
            lines += [f"## {payload}", ""]
        elif kind == "h2":
            lines += [f"### {payload}", ""]
        elif kind == "h3":
            lines += [f"#### {payload}", ""]
        elif kind == "p":
            lines += [payload, ""]
        elif kind == "bullets":
            lines += [f"- {item}" for item in payload] + [""]
        elif kind == "img":
            filename, caption, _ = payload
            lines += [f"![{caption}](figures/{filename})", "", f"*{caption}*", ""]
        elif kind == "table":
            (header, rows, _), caption = payload
            lines += [f"**{caption}**", ""]
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join(["---"] * len(header)) + " |")
            for row in rows:
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    return OUT_MD


def main() -> int:
    figures.main()
    docx_path = render_docx()
    md_path = render_md()
    print(f"报告（Word）-> {docx_path}")
    print(f"报告（Markdown）-> {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())