"""Script node contracts exercised through the same executor used by workflows."""
from __future__ import annotations

import asyncio
import threading
import time
import unittest
from unittest.mock import patch

from app.services.agent_app.executors import script
from app.services.agent_app.workflow_run_ctx import WorkflowRunContext


class TestWorkflowScriptContract(unittest.TestCase):
    def make_context(self, **overrides):
        values = dict(
            db=None, run_id="script-contract", agent_app_id=1, version_id=1,
            inputs={}, call_stack=[], nodes_by_id={}, nodes=[], edges=[],
            var_to_id={"开始": "start"}, id_to_var={"start": "开始"}, context={},
        )
        values.update(overrides)
        return WorkflowRunContext(**values)

    def run_script(self, code, *, inputs=None, outputs=None, context=None):
        return asyncio.run(script.execute(context or self.make_context(), {
            "data": {"script_config": {
                "code": code, "input_vars": inputs or [], "output_vars": outputs or [],
            }},
        }))

    def test_typed_constants_arrive_as_python_values(self):
        cases = [
            ("NUMBER", "2", 2), ("number", "1.25", 1.25),
            ("BOOL", "false", False), ("boolean", "true", True),
            ("OBJECT", '{"a":2}', {"a": 2}),
            ("array_string", '["a","b"]', ["a", "b"]),
            ("LIST<Number>", "[0,2.5]", [0, 2.5]),
            ("array_boolean", "[false,true]", [False, True]),
            ("LIST<Object>", '[{"a":1}]', [{"a": 1}]),
            ("string", "false", "false"), ("string", "", ""),
        ]
        for kind, value, expected in cases:
            with self.subTest(kind=kind, value=value):
                actual = self.run_script("def main(value):\n    return {'result': value}", inputs=[{
                    "name": "value", "source_mode": "const", "type": kind, "const_value": value,
                }])
                self.assertEqual(actual, {"result": expected})
                self.assertIs(type(actual["result"]), type(expected))

    def test_invalid_typed_constants_explain_the_field(self):
        for kind, value in [("number", "oops"), ("boolean", "yes"),
                            ("object", "[]"), ("array_number", '[1,"two"]'),
                            ("number", "NaN"), ("number", True)]:
            with self.subTest(kind=kind, value=value):
                with self.assertRaisesRegex(ValueError, "输入变量 value"):
                    self.run_script("def main(value):\n    return {'result': value}", inputs=[{
                        "name": "value", "source_mode": "const", "type": kind, "const_value": value,
                    }])

    def test_input_and_metadata_are_valid_user_parameter_names(self):
        out = self.run_script("def main(input, metadata):\n    return {'result': input, 'metadata': metadata}", inputs=[
            {"name": "input", "source_mode": "const", "const_value": "hello"},
            {"name": "metadata", "source_mode": "const", "const_value": "custom"},
        ])
        self.assertEqual(out, {"result": "hello", "metadata": "custom"})

    def test_falsy_default_input_and_references_are_preserved(self):
        for value in [False, 0, [], {}, ""]:
            with self.subTest(value=value):
                ctx = self.make_context(inputs={"input": value, "message": "fallback"})
                out = self.run_script("def main(value):\n    return {'result': value}",
                                      inputs=[{"name": "value", "source_mode": "ref", "ref": ""}], context=ctx)
                self.assertEqual(out, {"result": value})

    def test_declared_reference_types_are_checked(self):
        ctx = self.make_context(context={"start": {"value": "2"}})
        with self.assertRaisesRegex(ValueError, "输入变量 value.*number"):
            self.run_script("def main(value):\n    return {'result': value}", inputs=[{
                "name": "value", "source_mode": "ref", "type": "number", "ref": "开始.value",
            }], context=ctx)

    def test_declared_nullable_value_is_preserved(self):
        out = self.run_script("def main(value):\n    return {'result': value}", inputs=[{
            "name": "value", "type": "object", "source_mode": "const", "const_value": None,
        }], outputs=[{"name": "result", "type": "object"}])
        self.assertEqual(out, {"result": None})

    def test_invalid_and_duplicate_input_names_are_rejected(self):
        for names in [["bad-name"], ["for"], ["_private"], ["value", "value"]]:
            with self.subTest(names=names):
                with self.assertRaisesRegex(ValueError, "输入变量"):
                    self.run_script("def main(**kwargs):\n    return kwargs", inputs=[{
                        "name": name, "source_mode": "const", "const_value": 1,
                    } for name in names])

    def test_missing_or_extra_parameters_have_actionable_error(self):
        cases = [
            ("def main(value):\n    return {'result': value}", [], "value"),
            ("def main():\n    return {'result': 1}", [{"name": "extra", "source_mode": "const", "const_value": 1}], "extra"),
        ]
        for code, inputs, parameter in cases:
            with self.subTest(parameter=parameter):
                with self.assertRaisesRegex(ValueError, "main 参数与输入变量不匹配.*" + parameter):
                    self.run_script(code, inputs=inputs)

    def test_default_and_keyword_only_main_parameters_work(self):
        out = self.run_script("def main(*, value=2):\n    return {'result': value}")
        self.assertEqual(out, {"result": 2})

    def test_common_python_operations_and_print_work(self):
        out = self.run_script("""
def main():
    total = 0
    rows = []
    for index, value in enumerate([2, 3]):
        total += value
        rows += [index]
    print('total', total)
    return {'total': total, 'rows': rows, 'log': printed}
""")
        self.assertEqual(out, {"total": 5, "rows": [0, 1], "log": "total 5\n"})

    def test_module_helpers_work_during_top_level_execution(self):
        out = self.run_script("""
PREFIX = 'item'
def label(value):
    return PREFIX + str(value)
LABELS = [label(value) for value in range(2)]
def main():
    return {'result': LABELS}
""")
        self.assertEqual(out, {"result": ["item0", "item1"]})

    def test_simple_class_definition_works(self):
        out = self.run_script("""
class Formatter:
    def label(self, value):
        return 'item-' + str(value)
def main():
    return {'result': Formatter().label(2)}
""")
        self.assertEqual(out, {"result": "item-2"})

    def test_missing_output_field_is_reported_even_after_partial_match(self):
        for code in ["def main():\n    return {'other': 1}", "def main():\n    return {'result': 1}"]:
            with self.subTest(code=code):
                with self.assertRaisesRegex(ValueError, "缺少已声明的输出变量.*missing"):
                    self.run_script(code, outputs=[{"name": "result"}, {"name": "missing"}])

    def test_extra_outputs_are_filtered(self):
        out = self.run_script("def main():\n    return {'result': 1, 'extra': 2}", outputs=[{"name": "result", "type": "number"}])
        self.assertEqual(out, {"result": 1})

    def test_output_type_mismatches_are_reported_without_coercion(self):
        for kind, literal in [("number", "'2'"), ("number", "True"), ("array_number", "[1, 'two']")]:
            with self.subTest(kind=kind, literal=literal):
                with self.assertRaisesRegex(ValueError, "输出变量 result"):
                    self.run_script(f"def main():\n    return {{'result': {literal}}}", outputs=[{"name": "result", "type": kind}])

    def test_duplicate_output_names_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "输出变量.*重复"):
            self.run_script("def main():\n    return {'result': 1}", outputs=[{"name": "result"}, {"name": "result"}])

    def test_non_json_result_fails_at_script_node(self):
        for literal in ["{1, 2}", "float('nan')", "b'raw'", "{1: 'numeric key'}"]:
            with self.subTest(literal=literal):
                with self.assertRaisesRegex(ValueError, "输出.*JSON"):
                    self.run_script(f"def main():\n    return {{'result': {literal}}}")

    def test_non_dict_result_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "main 必须返回 dict"):
            self.run_script("def main():\n    return ['a']")

    def test_empty_output_alias_does_not_replace_user_result_with_input(self):
        for value in ["", False, 0, None]:
            with self.subTest(value=value):
                out = self.run_script("def main(value):\n    return {'output': value}", inputs=[{
                    "name": "value", "source_mode": "const", "const_value": value,
                }], outputs=[{"name": "result"}], context=self.make_context(inputs={"input": "fallback"}))
                self.assertEqual(out, {"result": value})

    def test_legacy_execute_params_cache_and_thought_are_compatible(self):
        ctx = self.make_context(inputs={"input": "question", "messages": []})
        out = self.run_script("""
def execute_result(params):
    cache_set('seen', params.input)
    thought(session, '【Tag_处理】完成')
    return {'input': cache_get('seen'), 'messages': params.metadata['messages']}
""", context=ctx)
        self.assertEqual(out, {"result": {"input": "question", "messages": []}})
        self.assertEqual(ctx.thought_events[0]["tag"], "处理")

    def test_cancelling_a_running_script_does_not_block_the_event_loop(self):
        ctx = self.make_context()

        async def run():
            task = asyncio.create_task(script.execute(ctx, {"data": {"script_config": {
                "code": "def main():\n    thought('started')\n    time.sleep(30)\n    return {'result': 'late'}"
            }}}))
            try:
                async with asyncio.timeout(10):
                    while not ctx.thought_events:
                        await asyncio.sleep(0.01)
                begin = time.perf_counter()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertLess(time.perf_counter() - begin, 0.5)
            finally:
                task.cancel()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
