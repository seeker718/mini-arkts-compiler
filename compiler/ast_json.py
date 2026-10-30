"""AST -> JSON 序列化。

通过 ``dataclasses.fields`` 反射遍历节点字段，因此新增 AST 节点类型无需修改
本模块。输出的 JSON 结构固定为::

    {"type": "Program", "line": 1, "column": 1, "body": [...]}

``lineno`` / ``col`` 被重命名为更直观的 ``line`` / ``column``。
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from typing import Any

from .ast_nodes import Node


def to_jsonable(value: Any) -> Any:
    """把任意 AST 值递归转换为可 JSON 序列化的原生类型。"""
    if isinstance(value, Node):
        return node_to_dict(value)
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    return value


def node_to_dict(node: Node) -> dict:
    kind = type(node).__name__
    result: dict[str, Any] = {"type": kind}
    for f in fields(node):
        value = getattr(node, f.name)
        if f.name == "lineno":
            result["line"] = value
        elif f.name == "col":
            result["column"] = value
        else:
            result[f.name] = to_jsonable(value)
    return result


def to_json(node: Node, indent: int = 2) -> str:
    """AST 节点转 JSON 字符串。"""
    return json.dumps(node_to_dict(node), indent=indent, ensure_ascii=False)


def to_sexpr(node: Any) -> str:
    """生成紧凑的 S-表达式，便于在终端快速查看 AST，也方便单元测试断言。"""
    if isinstance(node, Node):
        if not is_dataclass(node):
            return type(node).__name__
        kind = type(node).__name__
        parts = []
        for f in fields(node):
            if f.name in ("lineno", "col"):
                continue
            value = getattr(node, f.name)
            if value is None or value == [] or value == "":
                continue
            parts.append(f"{f.name}={to_sexpr(value)}")
        return f"({kind} {' '.join(parts)})"
    if isinstance(node, list):
        return "[" + " ".join(to_sexpr(item) for item in node) + "]"
    if isinstance(node, str):
        return node
    return str(node) if node is not None else "None"