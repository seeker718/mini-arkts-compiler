"""实验三 · 分布式调度模拟单元测试。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler import distributed, ir  # noqa: E402


def make_module() -> ir.IRModule:
    funcs = []
    for name, count in [("a", 10), ("b", 5), ("c", 20), ("d", 3)]:
        instructions = [
            ir.IRInstruction(op=ir.OP_ASSIGN, dst=f"%t{i}", args=["1"])
            for i in range(count)
        ]
        instructions.append(ir.IRInstruction(op=ir.OP_RET, args=["0"]))
        blocks = [ir.IRBasicBlock("entry", instructions)]
        funcs.append(ir.IRFunction(name=name, return_type="number", blocks=blocks))
    return ir.IRModule(name="m", functions=funcs)


class TestDistributed(unittest.TestCase):
    def test_default_devices_are_distinct(self):
        devices = distributed.default_devices()
        self.assertEqual(len(devices), 4)
        self.assertEqual(len({d.id for d in devices}), 4)

    def test_tasks_from_module_uses_instruction_count(self):
        tasks = distributed.tasks_from_module(make_module())
        costs = {t.name: t.cost for t in tasks}
        self.assertEqual(len(tasks), 4)
        self.assertEqual(costs["a"], 11)   # 10 条 assign + 1 条 ret
        self.assertEqual(costs["c"], 21)

    def test_every_task_is_assigned(self):
        tasks = distributed.tasks_from_module(make_module())
        devices = distributed.default_devices()
        for strategy in ("round_robin", "least_loaded", "data_locality"):
            result = distributed.schedule(tasks, devices, strategy)
            self.assertEqual(len(result.assignments), len(tasks))
            ids = sorted(item[0] for item in result.assignments)
            self.assertEqual(ids, list(range(len(tasks))))

    def test_round_robin_order(self):
        devices = distributed.default_devices()
        tasks = [
            distributed.TaskUnit(id=i, name=f"t{i}", function="f", cost=1.0)
            for i in range(4)
        ]
        result = distributed.schedule(tasks, devices, "round_robin")
        self.assertEqual([item[2] for item in result.assignments], [0, 1, 2, 3])

    def test_data_locality_prefers_source_device(self):
        devices = distributed.default_devices()
        tasks = [
            distributed.TaskUnit(id=i, name=f"t{i}", function="f", cost=1.0, data_device=2)
            for i in range(3)
        ]
        result = distributed.schedule(tasks, devices, "data_locality")
        for _, _, device_id in result.assignments:
            self.assertEqual(device_id, 2)

    def test_least_loaded_produces_positive_metrics(self):
        tasks = distributed.tasks_from_module(make_module())
        result = distributed.schedule(tasks, distributed.default_devices(), "least_loaded")
        self.assertGreater(result.makespan, 0)
        self.assertLessEqual(result.balance, 1.0)
        self.assertGreater(result.balance, 0.0)

    def test_compare_strategies_returns_all_three(self):
        tasks = distributed.tasks_from_module(make_module())
        results = distributed.compare_strategies(tasks, distributed.default_devices())
        self.assertEqual(set(results), {"round_robin", "least_loaded", "data_locality"})

    def test_report_contains_key_metrics(self):
        tasks = distributed.tasks_from_module(make_module())
        result = distributed.schedule(tasks, distributed.default_devices(), "least_loaded")
        text = result.report()
        self.assertIn("makespan", text)
        self.assertIn("balance", text)

    def test_empty_tasks(self):
        result = distributed.schedule([], distributed.default_devices(), "least_loaded")
        self.assertEqual(result.makespan, 0.0)
        self.assertEqual(result.balance, 1.0)


if __name__ == "__main__":
    unittest.main()