"""Mini-ArkTS 编译器 —— 《编译技术》课程实验一~四公共包。

模块划分：
    tokens.py       词法单元（Token）与 TokenType 定义
    diagnostics.py  统一的诊断信息（词法/语法/语义错误）
    lexer.py        词法分析器（实验一）
    ast_nodes.py    抽象语法树（AST）节点定义
    parser.py       递归下降语法分析器（实验一）
    ast_json.py     AST -> JSON 序列化（实验一可视化用）
    visualize.py    AST -> 可交互 HTML 可视化（实验一验收项）
"""

__all__ = ["__version__"]
__version__ = "0.1.0"