"""
智能体工作流：上下文解析与端到端子图执行（无真实 DB / Redis）。

运行（在 backend 目录下）:
  python -m unittest tests.test_agent_workflow_engine -v
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

# 与 tests/test_auth_service.py 一致：将 backend 根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.agent_app.workflow_run_ctx import (
    WorkflowRunContext,
    build_var_name_maps,
    flatten_exports,
    resolve_dotted,
    substitute_llm_prompt,
    substitute_template,
    topological_order,
    reachable_from,
)
from app.services.agent_app.workflow_engine import run_nested_agent_workflow


_trace_writers = [patch("app.services.agent_app.workflow_engine.agent_run_trace_set"),
                  patch("app.services.agent_app.workflow_engine.save_workflow_trace")]


def setUpModule():
    # These graph/executor tests use mock DB rows; persistence is a separate contract.
    for writer in _trace_writers:
        writer.start()


def tearDownModule():
    for writer in reversed(_trace_writers):
        writer.stop()


def _minimal_ctx(
    *,
    var_to_id: dict,
    id_to_var: dict,
    context: dict,
) -> WorkflowRunContext:
    return WorkflowRunContext(
        db=MagicMock(),
        run_id="test-run",
        agent_app_id=1,
        version_id=1,
        inputs={},
        call_stack=[],
        nodes_by_id={},
        nodes=[],
        edges=[],
        var_to_id=var_to_id,
        id_to_var=id_to_var,
        context=context,
    )


class TestBuildVarNameMaps(unittest.TestCase):
    def test_explicit_llm_names_unique(self):
        nodes = [
            {"id": "n1", "data": {"kind": "llm", "var_name": "LLM_1"}},
            {"id": "n2", "data": {"kind": "llm", "var_name": "LLM_2"}},
        ]
        var_to_id, id_to_var = build_var_name_maps(nodes)
        self.assertEqual(id_to_var["n1"], "LLM_1")
        self.assertEqual(id_to_var["n2"], "LLM_2")
        self.assertEqual(var_to_id["LLM_1"], "n1")

    def test_duplicate_var_name_raises(self):
        nodes = [
            {"id": "n1", "data": {"kind": "llm", "var_name": "dup"}},
            {"id": "n2", "data": {"kind": "script", "var_name": "dup"}},
        ]
        with self.assertRaises(ValueError) as cm:
            build_var_name_maps(nodes)
        self.assertIn("重复", str(cm.exception))

    def test_user_input_custom_var_name(self):
        nodes = [
            {"id": "u", "data": {"kind": "userInput", "var_name": "对话入口"}},
        ]
        var_to_id, id_to_var = build_var_name_maps(nodes)
        self.assertEqual(id_to_var["u"], "对话入口")
        self.assertEqual(var_to_id["对话入口"], "u")

    def test_label_priority_with_var_name_alias(self):
        nodes = [
            {"id": "n1", "data": {"kind": "llm", "label": "问题理解", "var_name": "LLM_1"}},
        ]
        var_to_id, id_to_var = build_var_name_maps(nodes)
        self.assertEqual(id_to_var["n1"], "问题理解")
        self.assertEqual(var_to_id["问题理解"], "n1")
        self.assertEqual(var_to_id["LLM_1"], "n1")


class TestResolveAndTemplate(unittest.TestCase):
    def test_resolve_dotted(self):
        var_to_id, id_to_var = build_var_name_maps(
            [
                {"id": "u", "data": {"kind": "userInput"}},
            ]
        )
        ctx = _minimal_ctx(
            var_to_id=var_to_id,
            id_to_var=id_to_var,
            context={"u": {"input": "world"}},
        )
        self.assertEqual(resolve_dotted(ctx, "用户输入.input"), "world")

    def test_substitute_template(self):
        var_to_id, id_to_var = build_var_name_maps(
            [
                {"id": "u", "data": {"kind": "userInput"}},
            ]
        )
        ctx = _minimal_ctx(
            var_to_id=var_to_id,
            id_to_var=id_to_var,
            context={"u": {"input": 42}},
        )
        self.assertEqual(
            substitute_template(ctx, "prefix {{用户输入.input}} suffix"),
            "prefix 42 suffix",
        )

    def test_substitute_llm_prompt_named_then_dotted(self):
        var_to_id, id_to_var = build_var_name_maps(
            [
                {"id": "u", "data": {"kind": "userInput"}},
            ]
        )
        ctx = _minimal_ctx(
            var_to_id=var_to_id,
            id_to_var=id_to_var,
            context={"u": {"q": "地区销售"}},
        )
        bindings = {"input": {"source_mode": "ref", "ref": "用户输入.q"}}
        text = "SYS {{input}} / {{用户输入.q}}"
        self.assertEqual(
            substitute_llm_prompt(ctx, text, bindings),
            "SYS 地区销售 / 地区销售",
        )

    def test_substitute_llm_prompt_named_const(self):
        var_to_id, id_to_var = build_var_name_maps([])
        ctx = _minimal_ctx(var_to_id=var_to_id, id_to_var=id_to_var, context={})
        bindings = {"x": {"source_mode": "const", "const_value": "hi"}}
        self.assertEqual(substitute_llm_prompt(ctx, "A{{x}}B", bindings), "AhiB")


class TestGraphAlgorithms(unittest.TestCase):
    def test_topological_order_linear(self):
        ids = reachable_from("a", [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}])
        self.assertEqual(ids, {"a", "b", "c"})
        order = topological_order(ids, [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}])
        self.assertEqual(order, ["a", "b", "c"])

    def test_topological_cycle_raises(self):
        ids = {"a", "b"}
        edges = [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]
        with self.assertRaises(ValueError) as cm:
            topological_order(ids, edges)
        self.assertIn("环", str(cm.exception))


class TestFlattenExports(unittest.TestCase):
    def test_flatten(self):
        id_to_var = {"n1": "用户输入", "n2": "输出"}
        ctx_map = {"n1": {"input": "x"}}
        exp = flatten_exports(ctx_map, id_to_var, "final")
        self.assertEqual(exp["output"], "final")
        self.assertEqual(exp["用户输入.input"], "x")


class TestRunNestedAgentWorkflow(unittest.TestCase):
    """开始 → 用户输入 → 输出，模板引用用户输入（与前端默认变量名一致）。"""

    def test_user_input_to_output_template(self):
        class FakeVersion:
            id = 99
            workflow_json = {
                "nodes": [
                    {"id": "a", "data": {"kind": "start", "label": "开始"}},
                    {
                        "id": "b",
                        "data": {
                            "kind": "userInput",
                            "label": "用户输入",
                            "fields": [{"variable": "input", "required": True}],
                        },
                    },
                    {
                        "id": "c",
                        "data": {
                            "kind": "output",
                            "label": "输出",
                            "output_config": {"content_template": "{{用户输入.input}}"},
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "a", "target": "b"},
                    {"id": "e2", "source": "b", "target": "c"},
                ],
            }

        db = MagicMock()

        async def _run():
            with patch(
                "app.services.agent_app.workflow_engine.get_version_for_app",
                return_value=FakeVersion(),
            ):
                return await run_nested_agent_workflow(
                    db,
                    agent_app_id=1,
                    version_id=1,
                    inputs={"input": "hello"},
                    call_stack=[],
                )

        result = asyncio.run(_run())
        self.assertEqual(result["output"], "hello")
        self.assertEqual(result["exports"].get("用户输入.input"), "hello")
        self.assertEqual(result["exports"].get("output"), "hello")

    def test_parallel_level_runs_concurrently(self):
        """
        图结构：start -> s1,s2(同层 script) -> output
        期望：s1/s2 并行，整体耗时接近单个节点耗时而不是两者串行和。
        """

        class FakeVersion:
            id = 100
            workflow_json = {
                "nodes": [
                    {"id": "a", "data": {"kind": "start", "label": "开始"}},
                    {
                        "id": "s1",
                        "data": {
                            "kind": "script",
                            "label": "脚本1",
                            "var_name": "脚本_1",
                            "script_config": {},
                        },
                    },
                    {
                        "id": "s2",
                        "data": {
                            "kind": "script",
                            "label": "脚本2",
                            "var_name": "脚本_2",
                            "script_config": {},
                        },
                    },
                    {
                        "id": "o",
                        "data": {
                            "kind": "output",
                            "label": "输出",
                            "output_config": {"content_template": "ok"},
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "a", "target": "s1"},
                    {"id": "e2", "source": "a", "target": "s2"},
                    {"id": "e3", "source": "s1", "target": "o"},
                    {"id": "e4", "source": "s2", "target": "o"},
                ],
            }

        async def fake_script(ctx, node):
            await asyncio.sleep(0.15)
            return {"name": node["id"]}

        db = MagicMock()

        async def _run():
            from app.services.agent_app import workflow_engine as we

            with patch(
                "app.services.agent_app.workflow_engine.get_version_for_app",
                return_value=FakeVersion(),
            ):
                old = we._KIND_HANDLERS["script"]
                we._KIND_HANDLERS["script"] = fake_script
                try:
                    t0 = time.perf_counter()
                    out = await run_nested_agent_workflow(
                        db,
                        agent_app_id=1,
                        version_id=1,
                        inputs={},
                        call_stack=[],
                    )
                    elapsed = time.perf_counter() - t0
                    return out, elapsed
                finally:
                    we._KIND_HANDLERS["script"] = old

        result, elapsed = asyncio.run(_run())
        self.assertEqual(result["output"], "ok")
        # 并行下应显著小于串行约 0.30s；给 CI 预留余量
        self.assertLess(elapsed, 0.27)

    def test_selector_prunes_to_one_branch_then_merge_output(self):
        """选择器剪枝后仅执行命中分支，两路脚本汇合到同一输出。"""

        class FakeVersion:
            id = 101
            workflow_json = {
                "nodes": [
                    {"id": "a", "data": {"kind": "start", "label": "开始"}},
                    {
                        "id": "b",
                        "data": {
                            "kind": "userInput",
                            "label": "用户输入",
                            "fields": [{"variable": "input", "required": True}],
                        },
                    },
                    {
                        "id": "c",
                        "data": {
                            "kind": "selector",
                            "label": "选择",
                            "selector_config": {
                                "cases": [
                                    {
                                        "id": "case-0",
                                        "conditions": [
                                            {"ref": "用户输入.input", "op": "starts_with", "value": "x"}
                                        ],
                                    }
                                ]
                            },
                        },
                    },
                    {"id": "d", "data": {"kind": "script", "label": "分支A", "script_config": {}}},
                    {"id": "e", "data": {"kind": "script", "label": "分支B", "script_config": {}}},
                    {
                        "id": "o",
                        "data": {
                            "kind": "output",
                            "label": "输出",
                            "output_config": {
                                "content_template": "{{分支A.result}}{{分支B.result}}"
                            },
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "a", "target": "b"},
                    {"id": "e2", "source": "b", "target": "c"},
                    {"id": "e3", "source": "c", "target": "d", "sourceHandle": "case-0"},
                    {"id": "e4", "source": "c", "target": "e", "sourceHandle": "else"},
                    {"id": "e5", "source": "d", "target": "o"},
                    {"id": "e6", "source": "e", "target": "o"},
                ],
            }

        async def fake_script(ctx, node):
            nid = node["id"]
            if nid == "d":
                return {"result": "A"}
            if nid == "e":
                return {"result": "B"}
            return {}

        db = MagicMock()

        async def _run(inp: str):
            from app.services.agent_app import workflow_engine as we

            with patch(
                "app.services.agent_app.workflow_engine.get_version_for_app",
                return_value=FakeVersion(),
            ):
                old = we._KIND_HANDLERS["script"]
                we._KIND_HANDLERS["script"] = fake_script
                try:
                    return await run_nested_agent_workflow(
                        db,
                        agent_app_id=1,
                        version_id=1,
                        inputs={"input": inp},
                        call_stack=[],
                    )
                finally:
                    we._KIND_HANDLERS["script"] = old

        out_x = asyncio.run(_run("xray"))
        self.assertEqual(out_x["output"], "A")

        out_y = asyncio.run(_run("hello"))
        self.assertEqual(out_y["output"], "B")


class TestUserInputExecutor(unittest.TestCase):
    def test_ref_fallback_uses_top_level_input(self):
        from app.services.agent_app.executors import user_input as ex_user_input

        async def _run():
            var_to_id, id_to_var = build_var_name_maps(
                [{"id": "u", "data": {"kind": "userInput", "var_name": "用户输入"}}]
            )
            ctx = WorkflowRunContext(
                db=MagicMock(),
                run_id="r",
                agent_app_id=1,
                version_id=1,
                inputs={"input": "hello"},
                call_stack=[],
                nodes_by_id={},
                nodes=[],
                edges=[],
                var_to_id=var_to_id,
                id_to_var=id_to_var,
                context={},
            )
            node = {
                "data": {
                    "fields": [
                        {
                            "variable": "q",
                            "source_mode": "ref",
                            "source_ref": ["input", "input"],
                            "required": True,
                        }
                    ]
                }
            }
            return await ex_user_input.execute(ctx, node)

        out = asyncio.run(_run())
        self.assertEqual(out["q"], "hello")


class TestScriptAndAgentConstInput(unittest.TestCase):
    def test_script_input_vars_support_const(self):
        from app.services.agent_app.executors import script as ex_script

        async def _run():
            ctx = WorkflowRunContext(
                db=MagicMock(),
                run_id="r",
                agent_app_id=1,
                version_id=1,
                inputs={},
                call_stack=[],
                nodes_by_id={},
                nodes=[],
                edges=[],
                var_to_id={},
                id_to_var={},
                context={},
            )
            node = {
                "data": {
                    "script_config": {
                        "code": "def main(x):\n    return {'result': x}\n",
                        "input_vars": [{"name": "x", "source_mode": "const", "const_value": "A"}],
                        "output_vars": [{"name": "result"}],
                    }
                }
            }
            return await ex_script.execute(ctx, node)

        out = asyncio.run(_run())
        self.assertEqual(out["result"], "A")

    def test_script_supports_string_slicing_and_indexing(self):
        from app.services.agent_app.executors import script as ex_script

        async def _run():
            ctx = WorkflowRunContext(
                db=MagicMock(),
                run_id="r",
                agent_app_id=1,
                version_id=1,
                inputs={},
                call_stack=[],
                nodes_by_id={},
                nodes=[],
                edges=[],
                var_to_id={},
                id_to_var={},
                context={},
            )
            code = (
                "def main(arg1: str):\n"
                "    result = arg1\n"
                "    if 'where' in result.lower():\n"
                "        idx = result.lower().index('where')\n"
                "        result = result[:idx] + 'where 1=1 and ' + result[idx + 5:]\n"
                "    return {'result': result}\n"
            )
            node = {
                "data": {
                    "script_config": {
                        "code": code,
                        "input_vars": [
                            {
                                "name": "arg1",
                                "source_mode": "const",
                                "const_value": "select * from abc where 123",
                            }
                        ],
                        "output_vars": [{"name": "result"}],
                    }
                }
            }
            return await ex_script.execute(ctx, node)

        out = asyncio.run(_run())
        self.assertEqual(out["result"], "select * from abc where 1=1 and  123")

    def test_script_supports_sqlparse_import(self):
        from app.services.agent_app.executors import script as ex_script

        async def _run():
            ctx = WorkflowRunContext(
                db=MagicMock(),
                run_id="r",
                agent_app_id=1,
                version_id=1,
                inputs={},
                call_stack=[],
                nodes_by_id={},
                nodes=[],
                edges=[],
                var_to_id={},
                id_to_var={},
                context={},
            )
            node = {
                "data": {
                    "script_config": {
                        "code": "import sqlparse\n\ndef main(sql):\n    return {'result': sqlparse.format(sql, keyword_case='upper')}\n",
                        "input_vars": [
                            {"name": "sql", "source_mode": "const", "const_value": "select * from abc"}
                        ],
                        "output_vars": [{"name": "result"}],
                    }
                }
            }
            return await ex_script.execute(ctx, node)

        out = asyncio.run(_run())
        self.assertEqual(out["result"], "SELECT * FROM abc")

    def test_script_supports_json_and_typing_imports(self):
        from app.services.agent_app.executors import script as ex_script

        async def _run(text='{"questions":["问题1","问题2"]}'):
            ctx = WorkflowRunContext(
                db=MagicMock(),
                run_id="r",
                agent_app_id=1,
                version_id=1,
                inputs={},
                call_stack=[],
                nodes_by_id={},
                nodes=[],
                edges=[],
                var_to_id={},
                id_to_var={},
                context={},
            )
            code = (
                "import json\n"
                "from typing import Any, Dict, List\n\n"
                "def main(text: str):\n"
                "    try:\n"
                "        data = json.loads(text)\n"
                "    except json.JSONDecodeError as e:\n"
                "        raise ValueError(f'无效的 JSON 格式: {e}')\n"
                "    questions = data.get('questions', [])\n"
                "    if not isinstance(questions, list):\n"
                "        raise TypeError(\"'questions' 字段必须是数组\")\n"
                "    q1, q2, q3, q4 = (questions[:4] + [''] * 4)[:4]\n"
                "    return {'q1': q1, 'q2': q2, 'q3': q3, 'q4': q4}\n"
            )
            node = {
                "data": {
                    "script_config": {
                        "code": code,
                        "input_vars": [
                            {
                                "name": "text",
                                "source_mode": "const",
                                "const_value": text,
                            }
                        ],
                        "output_vars": [
                            {"name": "q1"},
                            {"name": "q2"},
                            {"name": "q3"},
                            {"name": "q4"},
                        ],
                    }
                }
            }
            return await ex_script.execute(ctx, node)

        out = asyncio.run(_run())
        self.assertEqual(
            out,
            {"q1": "问题1", "q2": "问题2", "q3": "", "q4": ""},
        )
        with self.assertRaisesRegex(ValueError, "无效的 JSON 格式"):
            asyncio.run(_run("not-json"))
        with self.assertRaisesRegex(TypeError, "'questions' 字段必须是数组"):
            asyncio.run(_run('{"questions":"not-a-list"}'))

    def test_script_supports_any_installed_absolute_import(self):
        from app.services.agent_app.executors import script as ex_script

        async def _run():
            ctx = WorkflowRunContext(
                db=MagicMock(),
                run_id="r",
                agent_app_id=1,
                version_id=1,
                inputs={},
                call_stack=[],
                nodes_by_id={},
                nodes=[],
                edges=[],
                var_to_id={},
                id_to_var={},
                context={},
            )
            code = (
                "import csv\n"
                "from pathlib import PurePosixPath\n\n"
                "def main(value):\n"
                "    cells = list(csv.reader([value]))[0]\n"
                "    return {'result': PurePosixPath('/tmp', cells[1]).name}\n"
            )
            node = {
                "data": {
                    "script_config": {
                        "code": code,
                        "input_vars": [
                            {"name": "value", "source_mode": "const", "const_value": "a,b.csv"}
                        ],
                        "output_vars": [{"name": "result"}],
                    }
                }
            }
            return await ex_script.execute(ctx, node)

        out = asyncio.run(_run())
        self.assertEqual(out["result"], "b.csv")

    def test_script_import_reports_missing_runtime_package(self):
        from app.services.agent_app.executors import script as ex_script

        with self.assertRaisesRegex(ImportError, "运行环境未安装模块: package_not_installed_123"):
            ex_script._runtime_import("package_not_installed_123")

    def test_script_import_rejects_relative_import(self):
        from app.services.agent_app.executors import script as ex_script

        with self.assertRaisesRegex(ImportError, "不支持相对导入"):
            ex_script._runtime_import("helpers", level=1)


class TestLabFeaturesAndOutputFilter(unittest.TestCase):
    def test_lab_executor_uses_features_const_and_filters_outputs(self):
        from app.services.agent_app.executors import lab as ex_lab

        async def _run():
            # 捕获 collect_autobi_lab_gateway_json 入参
            captured = {}

            async def fake_collect_autobi_lab_gateway_json(
                db,
                *,
                user_message,
                lab_config,
                kb_id,
                project_id,
                project_name,
                trace_id,
                trace_started_at,
                features=None,
            ):
                captured["user_message"] = user_message
                captured["lab_config"] = lab_config
                captured["features"] = features
                return {"trace_id": trace_id, "summary": "ok", "error": None}

            def fake_get_autobi_project_service(db, project_id: int):
                return {
                    "id": project_id,
                    "name": "Lab",
                    "config_json": {
                        "request": {
                            "advanced_config": {
                                "x": {"prompt": "hello {{foo}}"}
                            }
                        }
                    },
                    "knowledge_base_id": 1,
                }

            ctx = WorkflowRunContext(
                db=MagicMock(),
                run_id="r",
                agent_app_id=1,
                version_id=1,
                inputs={},
                call_stack=[],
                nodes_by_id={},
                nodes=[],
                edges=[],
                var_to_id={},
                id_to_var={},
                context={},
            )
            node = {
                "data": {
                    "lab_config": {
                        "project_id": 11,
                        "input_mapping": [
                            {"target_field": "content", "source_mode": "const", "const_value": "Q"},
                            {
                                "target_field": "features",
                                "source_mode": "const",
                                "const_value": '{"foo":"bar"}',
                            },
                        ],
                        "output_vars": ["summary"],
                    }
                }
            }

            with patch(
                "app.services.autobi.lab_runtime.get_autobi_project_service",
                side_effect=fake_get_autobi_project_service,
            ), patch(
                "app.services.autobi.lab_runtime.collect_autobi_lab_gateway_json",
                side_effect=fake_collect_autobi_lab_gateway_json,
            ):
                out = await ex_lab.execute(ctx, node)
                return out, captured

        out, captured = asyncio.run(_run())
        # outputs filter
        self.assertEqual(out, {"summary": "ok"})
        # features replacement
        adv = (captured["lab_config"].get("request") or {}).get("advanced_config") or {}
        self.assertEqual(adv["x"]["prompt"], "hello bar")
        self.assertEqual(captured["features"], {"foo": "bar", "history_question": "当前是新问题"})

    def test_lab_stream_executor_keeps_summary_output_and_thoughts(self):
        from app.services.agent_app.executors import lab as ex_lab
        from app.services.autobi.lab_runtime import LabRunSpec

        async def _run():
            async def fake_stream(db, spec, *, trace=None):
                self.assertIsNotNone(trace)
                yield (
                    'data: {"id":"s","index":1,"finish":false,"status_code":"SUCCESS",'
                    '"message":{"role":"assistant","type":"progress","content":"","features":{"progress":"生成SQL中"}}}\n\n'
                )
                yield (
                    'data: {"id":"s","index":2,"finish":false,"status_code":"SUCCESS",'
                    '"message":{"role":"assistant","type":"text","content":"hello","features":{}}}\n\n'
                )
                yield (
                    'data: {"id":"s","index":3,"finish":false,"status_code":"SUCCESS",'
                    '"message":{"role":"assistant","type":"text","content":" world","features":{}}}\n\n'
                )

            def fake_build_spec(db, project_id, *, content, features=None):
                return LabRunSpec(
                    content=content,
                    project_id=project_id,
                    project_name="Lab",
                    api_access_id="abc1234567",
                    knowledge_base_id=1,
                    lab_config={},
                    features=features or {},
                )

            ctx = WorkflowRunContext(
                db=MagicMock(),
                run_id="stream",
                agent_app_id=1,
                version_id=1,
                inputs={},
                call_stack=[],
                nodes_by_id={},
                nodes=[],
                edges=[],
                var_to_id={},
                id_to_var={},
                context={},
                stream=True,
            )
            node = {
                "data": {
                    "lab_config": {
                        "project_id": 11,
                        "input_mapping": [
                            {"target_field": "content", "source_mode": "const", "const_value": "Q"}
                        ],
                    }
                }
            }
            with patch(
                "app.services.agent_app.executors.lab.build_lab_run_spec_from_project_id",
                side_effect=fake_build_spec,
            ), patch(
                "app.services.agent_app.executors.lab.stream_lab_bailian_sse",
                side_effect=fake_stream,
            ):
                out = await ex_lab.execute(ctx, node)
                return out, ctx.thought_events

        out, thoughts = asyncio.run(_run())
        self.assertEqual(out["summary"], "hello world")
        self.assertEqual(len(thoughts), 4)
        self.assertEqual(thoughts[0]["payload"]["type"], "lab_trace")
        self.assertEqual(thoughts[0]["payload"]["trace_id"], out["trace_id"])
        self.assertNotEqual(out["trace_id"], "stream")
        self.assertEqual(thoughts[1]["payload"]["message"]["type"], "progress")


class TestWorkflowStreamThoughts(unittest.TestCase):
    def test_thought_event_is_yielded_while_node_is_still_running(self):
        from app.services.agent_app import workflow_engine

        class FakeVersion:
            id = 101
            workflow_json = {
                "nodes": [
                    {"id": "start", "data": {"kind": "start", "label": "开始"}},
                    {"id": "work", "data": {"kind": "script", "label": "脚本"}},
                    {"id": "out", "data": {"kind": "output", "label": "输出"}},
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "work"},
                    {"id": "e2", "source": "work", "target": "out"},
                ],
            }

        async def fake_script(ctx, node):
            await asyncio.sleep(0.01)
            ctx.thought_events.append({
                "tag": "实验室",
                "raw": "",
                "payload": {
                    "message": {
                        "type": "progress",
                        "content": "",
                        "features": {"progress": "生成SQL中..."},
                    }
                },
            })
            await asyncio.sleep(0.2)
            return {"content": "done"}

        async def _run():
            original_script = workflow_engine._KIND_HANDLERS["script"]
            workflow_engine._KIND_HANDLERS["script"] = fake_script
            try:
                with patch(
                    "app.services.agent_app.workflow_engine.get_version_for_app",
                    return_value=FakeVersion(),
                ):
                    gen = workflow_engine.run_agent_workflow_stream(
                        MagicMock(),
                        agent_app_id=1,
                        version_id=101,
                        inputs={},
                    )
                    # Progress events include both running and done; thoughts must
                    # still arrive before the slow executor has completed.
                    t0 = time.perf_counter()
                    async def next_thought():
                        async for event in gen:
                            if '"type": "thought"' in event:
                                return event
                        raise AssertionError("Thought event was not emitted")
                    thought_chunk = await asyncio.wait_for(next_thought(), timeout=0.12)
                    elapsed = time.perf_counter() - t0
                    await gen.aclose()
                    return thought_chunk, elapsed
            finally:
                workflow_engine._KIND_HANDLERS["script"] = original_script

        chunk, elapsed = asyncio.run(_run())
        self.assertLess(elapsed, 0.12)
        self.assertIn('"type": "thought"', chunk)
        self.assertIn("生成SQL中", chunk)

    def test_nested_agent_thought_event_is_yielded_in_parent_stream(self):
        from app.services.agent_app import workflow_engine

        def make_parent_version(sse_output_thoughts=True):
            class ParentVersion:
                id = 201
                workflow_json = {
                    "nodes": [
                        {"id": "start", "data": {"kind": "start", "label": "开始"}},
                        {
                            "id": "agent",
                            "data": {
                                "kind": "agent",
                                "label": "子智能体",
                                "agent_config": {
                                    "target_app_id": 2,
                                    "target_version_id": 202,
                                    "input_mapping": [],
                                    "output_mapping": [{"source_field": "output", "target_var": "content"}],
                                    "sse_output_thoughts": sse_output_thoughts,
                                },
                            },
                        },
                        {"id": "out", "data": {"kind": "output", "label": "输出"}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "start", "target": "agent"},
                        {"id": "e2", "source": "agent", "target": "out"},
                    ],
                }

            return ParentVersion()

        class ChildVersion:
            id = 202
            workflow_json = {
                "nodes": [
                    {"id": "start", "data": {"kind": "start", "label": "开始"}},
                    {"id": "work", "data": {"kind": "script", "label": "脚本"}},
                    {"id": "out", "data": {"kind": "output", "label": "输出"}},
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "work"},
                    {"id": "e2", "source": "work", "target": "out"},
                ],
            }

        async def fake_script(ctx, node):
            self.assertTrue(ctx.stream)
            await asyncio.sleep(0.01)
            ctx.thought_events.append({
                "tag": "实验室",
                "raw": "",
                "payload": {
                    "message": {
                        "type": "progress",
                        "content": "",
                        "features": {"progress": "子智能体生成中..."},
                    }
                },
            })
            await asyncio.sleep(0.2)
            return {"content": "child done"}

        def fake_get_version(db, agent_app_id, version_id):
            if int(agent_app_id) == 1:
                return make_parent_version()
            if int(agent_app_id) == 2:
                return ChildVersion()
            return None

        async def _run():
            original_script = workflow_engine._KIND_HANDLERS["script"]
            workflow_engine._KIND_HANDLERS["script"] = fake_script
            try:
                with patch("app.services.agent_app.workflow_engine.get_version_for_app", side_effect=fake_get_version), patch(
                    "app.services.agent_app.executors.agent.get_version_for_app",
                    side_effect=fake_get_version,
                ):
                    gen = workflow_engine.run_agent_workflow_stream(
                        MagicMock(),
                        agent_app_id=1,
                        version_id=201,
                        inputs={},
                    )
                    # Progress events include both running and done; thoughts must
                    # still arrive before the slow executor has completed.
                    t0 = time.perf_counter()
                    async def next_thought():
                        async for event in gen:
                            if '"type": "thought"' in event:
                                return event
                        raise AssertionError("Thought event was not emitted")
                    thought_chunk = await asyncio.wait_for(next_thought(), timeout=0.12)
                    elapsed = time.perf_counter() - t0
                    await gen.aclose()
                    return thought_chunk, elapsed
            finally:
                workflow_engine._KIND_HANDLERS["script"] = original_script

        chunk, elapsed = asyncio.run(_run())
        self.assertLess(elapsed, 0.12)
        self.assertIn('"type": "thought"', chunk)
        self.assertIn("子智能体生成中", chunk)

    def test_nested_agent_can_disable_parent_stream_passthrough(self):
        from app.services.agent_app import workflow_engine

        class ParentVersion:
            id = 201
            workflow_json = {
                "nodes": [
                    {"id": "start", "data": {"kind": "start", "label": "开始"}},
                    {
                        "id": "agent",
                        "data": {
                            "kind": "agent",
                            "label": "子智能体",
                            "agent_config": {
                                "target_app_id": 2,
                                "target_version_id": 202,
                                "input_mapping": [],
                                "output_mapping": [{"source_field": "output", "target_var": "content"}],
                                "sse_output_thoughts": False,
                            },
                        },
                    },
                    {"id": "out", "data": {"kind": "output", "label": "输出"}},
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "agent"},
                    {"id": "e2", "source": "agent", "target": "out"},
                ],
            }

        class ChildVersion:
            id = 202
            workflow_json = {
                "nodes": [
                    {"id": "start", "data": {"kind": "start", "label": "开始"}},
                    {"id": "work", "data": {"kind": "script", "label": "脚本"}},
                    {"id": "out", "data": {"kind": "output", "label": "输出"}},
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "work"},
                    {"id": "e2", "source": "work", "target": "out"},
                ],
            }

        async def fake_script(ctx, node):
            self.assertFalse(ctx.stream)
            await asyncio.sleep(0.01)
            ctx.thought_events.append({
                "tag": "实验室",
                "raw": "",
                "payload": {
                    "message": {
                        "type": "progress",
                        "content": "",
                        "features": {"progress": "子智能体生成中..."},
                    }
                },
            })
            await asyncio.sleep(0.2)
            return {"content": "child done"}

        def fake_get_version(db, agent_app_id, version_id):
            if int(agent_app_id) == 1:
                return ParentVersion()
            if int(agent_app_id) == 2:
                return ChildVersion()
            return None

        async def _run():
            original_script = workflow_engine._KIND_HANDLERS["script"]
            workflow_engine._KIND_HANDLERS["script"] = fake_script
            try:
                with patch("app.services.agent_app.workflow_engine.get_version_for_app", side_effect=fake_get_version), patch(
                    "app.services.agent_app.executors.agent.get_version_for_app",
                    side_effect=fake_get_version,
                ):
                    gen = workflow_engine.run_agent_workflow_stream(
                        MagicMock(),
                        agent_app_id=1,
                        version_id=201,
                        inputs={},
                    )
                    # start 节点完成事件
                    await asyncio.wait_for(gen.__anext__(), timeout=0.2)
                    chunks = []
                    for _ in range(3):
                        chunks.append(await asyncio.wait_for(gen.__anext__(), timeout=0.4))
                    await gen.aclose()
                    return "".join(chunks)
            finally:
                workflow_engine._KIND_HANDLERS["script"] = original_script

        chunks = asyncio.run(_run())
        self.assertNotIn('"type": "thought"', chunks)
        self.assertNotIn("子智能体生成中", chunks)
        self.assertIn("child done", chunks)


if __name__ == "__main__":
    unittest.main()
