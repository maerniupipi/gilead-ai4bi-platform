"""Parallel execution must agree with streaming about the workflow's result."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.services.agent_app import workflow_engine
from app.services.agent_app.workflow_run_ctx import WorkflowRunContext, build_var_name_maps, substitute_llm_prompt


class TestWorkflowExecutionConsistency(unittest.TestCase):
    def test_inserted_llm_values_remain_literal_template_text(self):
        nodes, edges = self.graph()
        ctx = self.context(nodes, edges)
        text = "请解释 {{customer.name}}、{{input}} 和 ${input} 的含义"
        ctx.inputs = {"input": text}
        self.assertEqual(substitute_llm_prompt(ctx, "问题：{{input}}"), "问题：" + text)
        self.assertEqual(substitute_llm_prompt(ctx, "问题：${input}"), "问题：" + text)

    def graph(self, *, two_outputs=False):
        nodes = [
            {"id": "start", "data": {"kind": "start", "label": "开始"}},
            {"id": "a-output", "data": {"kind": "output", "label": "输出A"}},
            {"id": "z-sibling", "data": {"kind": "output" if two_outputs else "script", "label": "旁支B"}},
        ]
        edges = [{"source": "start", "target": target} for target in ["a-output", "z-sibling"]]
        return nodes, edges

    def context(self, nodes, edges):
        var_to_id, id_to_var = build_var_name_maps(nodes)
        return WorkflowRunContext(
            db=MagicMock(), run_id="consistency", agent_app_id=1, version_id=1,
            inputs={}, call_stack=[], nodes_by_id={node["id"]: node for node in nodes},
            nodes=nodes, edges=edges, var_to_id=var_to_id, id_to_var=id_to_var,
        )

    async def run_dynamic(self, nodes, edges):
        ctx = self.context(nodes, edges)
        error = await workflow_engine._run_workflow_dynamic(
            ctx, start_id="start", out_nid="a-output",
            out_nids={node["id"] for node in nodes if node["data"]["kind"] == "output"},
        )
        self.assertIsNone(error)
        return ctx.final_output

    async def run_stream(self, nodes, edges):
        version = SimpleNamespace(workflow_json={"nodes": nodes, "edges": edges})
        with patch.object(workflow_engine, "get_version_for_app", return_value=version), \
                patch.object(workflow_engine, "save_workflow_trace"):
            events = [json.loads(chunk.removeprefix("data: ")) async for chunk in
                      workflow_engine.run_agent_workflow_stream(MagicMock(), 1, 1, {})]
        self.assertEqual(events[-1]["status"], "done")
        return events[-1]["output"]

    def test_slow_parallel_node_cannot_replace_final_output(self):
        nodes, edges = self.graph()

        async def output(ctx, node):
            return {"content": "declared output"}

        async def sibling(ctx, node):
            await asyncio.sleep(0.01)
            return {"content": "side branch"}

        async def run():
            with patch.dict(workflow_engine._KIND_HANDLERS, {"output": output, "script": sibling}):
                self.assertEqual(await self.run_dynamic(nodes, edges), "declared output")
                self.assertEqual(await self.run_stream(nodes, edges), "declared output")

        asyncio.run(run())

    def test_empty_final_output_is_preserved(self):
        nodes, edges = self.graph()

        async def output(ctx, node):
            return {"content": ""}

        async def sibling(ctx, node):
            await asyncio.sleep(0.01)
            return {"text": "side branch"}

        async def run():
            with patch.dict(workflow_engine._KIND_HANDLERS, {"output": output, "script": sibling}):
                self.assertEqual(await self.run_dynamic(nodes, edges), "")
                self.assertEqual(await self.run_stream(nodes, edges), "")

        asyncio.run(run())

    def test_parallel_outputs_are_independent_of_completion_order_and_match_stream(self):
        nodes, edges = self.graph(two_outputs=True)

        async def run():
            results = []
            for slow_id in ["a-output", "z-sibling"]:
                async def output(ctx, node):
                    if node["id"] == slow_id:
                        await asyncio.sleep(0.01)
                    return {"content": node["id"]}

                with patch.dict(workflow_engine._KIND_HANDLERS, {"output": output}):
                    results.append(await self.run_dynamic(nodes, edges))
                    results.append(await self.run_stream(nodes, edges))
            self.assertIn(results[0], {"a-output", "z-sibling"})
            self.assertEqual(results, [results[0]] * 4)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
