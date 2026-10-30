"""实验四 · 模糊测试器单元测试。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.fuzzer import (  # noqa: E402
    FrontendRunner,
    FuzzCase,
    Fuzzer,
    FuzzReport,
    FuzzResult,
    GrammarFuzzer,
    Mutator,
)
from compiler.lexer import tokenize  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.sema import analyze  # noqa: E402


class TestGrammarFuzzer(unittest.TestCase):
    def test_generated_code_passes_frontend(self):
        fuzzer = GrammarFuzzer(seed=1)
        for _ in range(10):
            source = fuzzer.generate()
            tokens, lex_errors = tokenize(source)
            program, parse_errors = parse(tokens)
            sema_errors, _ = analyze(program)
            self.assertEqual(
                lex_errors + parse_errors + sema_errors, [],
                f"生成的代码不应有诊断：{source}",
            )

    def test_generation_is_deterministic(self):
        self.assertEqual(GrammarFuzzer(seed=5).generate(), GrammarFuzzer(seed=5).generate())

    def test_generation_varies_with_seed(self):
        sources = {GrammarFuzzer(seed=i).generate() for i in range(6)}
        self.assertGreater(len(sources), 1)


class TestMutator(unittest.TestCase):
    SRC = "function f(): number { let x: number = 1; return x; }"

    def test_mutation_changes_source(self):
        mutator = Mutator(seed=2)
        changed = sum(1 for _ in range(30) if mutator.mutate(self.SRC) != self.SRC)
        self.assertGreater(changed, 20)

    def test_mutation_is_deterministic(self):
        self.assertEqual(
            Mutator(seed=9).mutate(self.SRC),
            Mutator(seed=9).mutate(self.SRC),
        )

    def test_mutation_of_empty_source(self):
        self.assertEqual(Mutator(seed=1).mutate(""), "")


class TestRunner(unittest.TestCase):
    def test_classifies_ok(self):
        case = FuzzCase(1, "function f(): number { return 1; }", "grammar")
        self.assertEqual(FrontendRunner().run(case).outcome, "ok")

    def test_classifies_diagnostics(self):
        case = FuzzCase(2, "let x: number = 'a';", "mutate")
        self.assertEqual(FrontendRunner().run(case).outcome, "diagnostics")

    def test_classifies_crash_passthrough(self):
        """直接构造 crash 结果，验证去重指纹与统计。"""
        report = FuzzReport()
        for i in range(3):
            case = FuzzCase(i, "x", "mutate")
            report.results.append(
                FuzzResult(case, "crash", error_type="IndexError",
                           message="list index out of range")
            )
        report.results.append(
            FuzzResult(FuzzCase(9, "y", "mutate"), "crash",
                       error_type="TypeError", message="bad operand type")
        )
        stats = report.stats()
        self.assertEqual(stats["crash"], 4)
        self.assertEqual(stats["unique_crashes"], 2)

    def test_report_text_lists_groups(self):
        report = FuzzReport()
        report.results.append(
            FuzzResult(FuzzCase(0, "x", "mutate"), "crash",
                       error_type="IndexError", message="boom")
        )
        text = report.to_text()
        self.assertIn("IndexError", text)
        self.assertIn("去重后崩溃组", text)


class TestFuzzer(unittest.TestCase):
    def test_run_produces_requested_iterations(self):
        report = Fuzzer(seed=7).run(40)
        self.assertEqual(report.stats()["total"], 40)

    def test_run_is_deterministic(self):
        first = Fuzzer(seed=42).run(25)
        second = Fuzzer(seed=42).run(25)
        self.assertEqual([r.case.source for r in first.results],
                         [r.case.source for r in second.results])

    def test_seed_corpus_enables_mutation_strategy(self):
        report = Fuzzer(seed=3, seeds=[TestMutator.SRC]).run(40)
        strategies = {case.strategy for case in report.cases}
        self.assertIn("mutate", strategies)

    def test_grammar_cases_never_crash_frontend(self):
        report = Fuzzer(seed=11).run(50)
        grammar_results = [r for r in report.results if r.case.strategy == "grammar"]
        for result in grammar_results:
            self.assertNotEqual(result.outcome, "crash",
                                f"合法生成用例不应崩溃：{result.case.preview()}")


if __name__ == "__main__":
    unittest.main()