"""实验二 · 类型系统单元测试。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.types import (  # noqa: E402
    ANY,
    BOOLEAN,
    NUMBER,
    STRING,
    MemberInfo,
    Type,
    TypeKind,
    TypeRegistry,
    array_of,
    function_type,
    is_assignable,
)


class TestTypes(unittest.TestCase):
    def setUp(self):
        self.registry = TypeRegistry()

    def test_number_and_string_are_strictly_separate(self):
        self.assertFalse(is_assignable(NUMBER, STRING, self.registry))
        self.assertFalse(is_assignable(STRING, NUMBER, self.registry))

    def test_same_type_is_assignable(self):
        self.assertTrue(is_assignable(NUMBER, NUMBER, self.registry))
        self.assertTrue(is_assignable(BOOLEAN, BOOLEAN, self.registry))

    def test_any_is_compatible(self):
        self.assertTrue(is_assignable(NUMBER, ANY, self.registry))
        self.assertTrue(is_assignable(ANY, NUMBER, self.registry))

    def test_array_element_compatibility(self):
        self.assertTrue(is_assignable(array_of(NUMBER), array_of(NUMBER), self.registry))
        self.assertFalse(is_assignable(array_of(STRING), array_of(NUMBER), self.registry))

    def test_function_signature_compatibility(self):
        f_num = function_type([NUMBER, NUMBER], NUMBER)
        f_num_same = function_type([NUMBER, NUMBER], NUMBER)
        f_str = function_type([STRING, NUMBER], NUMBER)
        self.assertTrue(is_assignable(f_num, f_num_same, self.registry))
        self.assertFalse(is_assignable(f_str, f_num, self.registry))

    def test_class_subtype_assignment(self):
        base = Type(TypeKind.CLASS, "Base")
        derived = Type(TypeKind.CLASS, "Derived", bases=["Base"])
        self.registry.register(base)
        self.registry.register(derived)
        self.assertTrue(is_assignable(derived, base, self.registry))
        self.assertFalse(is_assignable(base, derived, self.registry))

    def test_interface_subtype_assignment(self):
        iface = Type(TypeKind.INTERFACE, "Shape")
        impl = Type(TypeKind.CLASS, "Circle", bases=["Shape"])
        self.registry.register(iface)
        self.registry.register(impl)
        self.assertTrue(is_assignable(impl, iface, self.registry))

    def test_member_lookup_through_bases(self):
        base = Type(TypeKind.CLASS, "Base")
        base.members["value"] = MemberInfo("value", NUMBER)
        derived = Type(TypeKind.CLASS, "Derived", bases=["Base"])
        self.registry.register(base)
        self.registry.register(derived)
        self.assertIsNotNone(self.registry.member(derived, "value"))
        self.assertIsNone(self.registry.member(derived, "missing"))

    def test_primitive_resolution(self):
        self.assertIs(self.registry.resolve("number"), NUMBER)
        self.assertIs(self.registry.resolve("string"), STRING)
        self.assertIsNone(self.registry.resolve("NoSuchType"))

    def test_type_display_name(self):
        self.assertEqual(str(array_of(NUMBER)), "number[]")
        self.assertEqual(str(function_type([NUMBER], STRING)), "(number) => string")


if __name__ == "__main__":
    unittest.main()