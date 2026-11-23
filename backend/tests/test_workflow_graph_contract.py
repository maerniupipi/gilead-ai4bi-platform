"""Graph, reference and SSE contracts, without external services."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.agent_app import workflow_engine as engine
from app.services.agent_app.workflow_run_ctx import WorkflowRunContext, resolve_dotted, substitute_template


def node(nid, kind, **config):
    return {"id": nid, "data": {"kind": kind, "label": nid, **config}}


def edge(source, target, handle=None):
    return {"source": source, "target": target, **({"sourceHandle": handle} if handle else {})}


class GraphContracts(unittest.TestCase):
    def setUp(self):
        self.writers = [patch.object(engine, "agent_run_trace_set"), patch.object(engine, "save_workflow_trace")]
        for writer in self.writers:
            writer.start()
            self.addCleanup(writer.stop)

    def version(self, nodes, edges):
        return SimpleNamespace(workflow_json={"nodes": nodes, "edges": edges})

    def events(self, version):
        async def collect():
            with patch.object(engine, "get_version_for_app", return_value=version):
                return [json.loads(chunk.removeprefix("data: ")) async for chunk in engine.run_agent_workflow_stream(MagicMock(), 1, 1, {})]
        return asyncio.run(collect())

    def test_any_reachable_output_is_accepted(self):
        engine.assert_runnable_workflow(self.version([node("s", "start"), node("unused", "output"), node("out", "output")], [edge("s", "out")]))

    def test_duplicate_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "ID 重复"):
            engine.assert_runnable_workflow(self.version([node("s", "start"), node("s", "output")], []))

    def test_duplicate_names_rejected_before_queue(self):
        with self.assertRaisesRegex(ValueError, "名称重复"):
            engine.assert_runnable_workflow(self.version([node("s", "start"), node("x", "script", label="重复"), node("o", "output", label="重复")], [edge("s", "o")]))

    def test_dangling_edge_rejected(self):
        with self.assertRaisesRegex(ValueError, "不存在的节点"):
            engine.assert_runnable_workflow(self.version([node("s", "start"), node("o", "output")], [edge("s", "ghost"), edge("s", "o")]))

    def test_sse_cycle_never_reports_success(self):
        events = self.events(self.version([node("s", "start"), node("o", "output")], [edge("s", "o"), edge("o", "s")]))
        self.assertTrue(any("环" in e.get("error", "") for e in events))
        self.assertFalse(any(e.get("status") == "done" for e in events))

    def test_sse_duplicate_names_become_error_event(self):
        events = self.events(self.version([node("s", "start"), node("a", "script", label="dup"), node("o", "output", label="dup")], [edge("s", "o")]))
        self.assertIn("名称重复", events[0]["error"])

    def test_sse_unconnected_selected_branch_fails(self):
        events = self.events(self.version([node("s", "start"), node("choice", "selector", selector_config={"cases": []}), node("o", "output")], [edge("s", "choice"), edge("choice", "o", "if-1")]))
        self.assertTrue(any("不可达" in (e.get("error") or "") for e in events))
        self.assertFalse(any(e.get("status") == "done" and not e.get("node_id") for e in events))

    def test_sse_exposes_running_and_real_snapshots(self):
        events = self.events(self.version([node("s", "start"), node("o", "output", output_config={"content_template": "hello"})], [edge("s", "o")]))
        running = [e for e in events if e.get("node_id") == "o" and e.get("status") == "running"]
        done = [e for e in events if e.get("node_id") == "o" and e.get("status") == "done"]
        self.assertEqual(running[0]["input_snapshot"]["rendered_content"], "hello")
        self.assertEqual(done[0]["output_snapshot"]["content"], "hello")
        self.assertEqual(events[-1]["output"], "hello")
        self.assertEqual(len(events[-1]["steps"]), 2)
        self.assertTrue(events[-1]["trace_id"])

    def test_nested_selector_can_finish_second_output(self):
        version = self.version([
            node("s", "start"), node("choice", "selector", selector_config={"cases": []}),
            node("a", "output", output_config={"content_template": "wrong"}),
            node("b", "output", output_config={"content_template": "correct"}),
        ], [edge("s", "choice"), edge("choice", "a", "if-1"), edge("choice", "b", "else")])
        with patch.object(engine, "get_version_for_app", return_value=version):
            result = asyncio.run(engine.run_nested_agent_workflow(MagicMock(), agent_app_id=1, version_id=1, inputs={}, call_stack=[]))
        self.assertEqual(result["output"], "correct")


class ReferenceContracts(unittest.TestCase):
    def setUp(self):
        self.ctx = WorkflowRunContext(db=MagicMock(), run_id="r", agent_app_id=1, version_id=1, inputs={}, call_stack=[], nodes_by_id={}, nodes=[], edges=[], var_to_id={"步骤.1": "n", "待执行": "later"}, id_to_var={"n": "步骤.1"}, context={"n": {"rows": [{"count": 0, "enabled": False}], "empty": None}})

    def test_array_paths_and_dotted_node_names(self):
        self.assertEqual(resolve_dotted(self.ctx, "步骤.1.rows.0.count"), 0)
        self.assertIs(resolve_dotted(self.ctx, "步骤.1.rows[0].enabled"), False)

    def test_missing_field_is_actionable(self):
        with self.assertRaisesRegex(ValueError, "字段不存在"):
            resolve_dotted(self.ctx, "步骤.1.typo")

    def test_unexecuted_branch_is_not_empty_success(self):
        with self.assertRaisesRegex(ValueError, "未执行"):
            resolve_dotted(self.ctx, "待执行.result")

    def test_explicit_null_remains_optional(self):
        self.assertIsNone(resolve_dotted(self.ctx, "步骤.1.empty"))

    def test_index_out_of_range_is_actionable(self):
        with self.assertRaisesRegex(ValueError, "下标越界"):
            resolve_dotted(self.ctx, "步骤.1.rows.5")

    def test_templates_serialize_structured_values_as_json(self):
        self.assertEqual(json.loads(substitute_template(self.ctx, "{{步骤.1.rows}}")), [{"count": 0, "enabled": False}])

    def test_template_typo_is_not_silently_swallowed(self):
        with self.assertRaisesRegex(ValueError, "字段不存在"):
            substitute_template(self.ctx, "answer: {{步骤.1.typo}}")


if __name__ == "__main__":
    unittest.main()
