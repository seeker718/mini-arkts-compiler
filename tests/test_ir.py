"""实验三 · IR 数据结构与打印单元测试。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler import ir  # noqa: E402


def _ret_block(value="1"):
    return ir.IRBasicBlock("entry", [ir.IRInstruction(op=ir.OP_RET, args=[value])])


class TestIR(unittest.TestCase):
    def test_binary_instruction_text(self):
        ins = ir.IRInstruction(op=ir.OP_ADD, dst="%t1", args=["%a", "%b"])
        self.assertEqual(ins.to_text(), "%t1 = add %a, %b")

    def test_branch_instruction_text(self):
        ins = ir.IRInstruction(op=ir.OP_BR, args=["%c", "L1", "L2"])
        self.assertEqual(ins.to_text(), "br %c, L1, L2")

    def test_phi_instruction_text(self):
        ins = ir.IRInstruction(
            op=ir.OP_PHI, dst="%x.2",
            args=[("%x", "if.then.1"), ("%x.1", "if.else.2")],
        )
        text = ins.to_text()
        self.assertIn("phi", text)
        self.assertIn("if.then.1", text)
        self.assertIn("if.else.2", text)

    def test_call_instruction_text(self):
        ins = ir.IRInstruction(op=ir.OP_CALL, dst="%t9", args=["fib", "%p0_n"])
        self.assertEqual(ins.to_text(), "%t9 = call fib(%p0_n)")

    def test_device_tag_in_text(self):
        ins = ir.IRInstruction(op=ir.OP_ADD, dst="%t1", args=["1", "2"], device=2)
        self.assertIn("dev=2", ins.to_text())

    def test_ret_without_value(self):
        self.assertEqual(ir.IRInstruction(op=ir.OP_RET).to_text(), "ret")

    def test_function_instruction_count(self):
        func = ir.IRFunction(name="f", return_type="number", blocks=[_ret_block()])
        self.assertEqual(func.instruction_count(), 1)

    def test_module_stats(self):
        func = ir.IRFunction(name="f", return_type="number", blocks=[_ret_block()])
        module = ir.IRModule(name="m", functions=[func])
        stats = module.stats()
        self.assertEqual(stats["functions"], 1)
        self.assertEqual(stats["blocks"], 1)
        self.assertEqual(stats["instructions"], 1)

    def test_module_text_contains_function_signature(self):
        func = ir.IRFunction(name="f", return_type="number", blocks=[_ret_block()])
        text = ir.IRModule(name="m", functions=[func]).to_text()
        self.assertIn("func f()", text)
        self.assertIn("ret 1", text)

    def test_cross_device_tag_in_function_text(self):
        func = ir.IRFunction(name="f", return_type="number", blocks=[_ret_block()],
                             cross_device=True, device_id=2)
        self.assertIn("cross-device", func.to_text())


if __name__ == "__main__":
    unittest.main()