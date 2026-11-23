"""Offline service fixtures with no external identity source."""
import json
from types import SimpleNamespace
import pytest
from tests.test_chatbi_credentials import api, make_key, headers, USER
from app.services.chatbi import chat, runtime
from app.services.agent_app.workflow_run_ctx import WorkflowRunContext


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def context(inputs):
    return WorkflowRunContext(db=None, run_id="test", agent_app_id=1, version_id=11,
        inputs=inputs, call_stack=[], nodes_by_id={}, nodes=[], edges=[], var_to_id={}, id_to_var={})


@pytest.fixture
def service_api(api, monkeypatch):
    from app.services.agent_app import workflow_engine
    _, key = make_key(api)
    seen = []
    async def engine(db, app_id, version_id, inputs, **kwargs):
        seen.append(inputs)
        yield {"status": "done", "output": "模拟分析结果"}
    monkeypatch.setattr(chat, "run_analysis", runtime.run_analysis)
    monkeypatch.setattr(workflow_engine, "run_agent_workflow_stream", engine)
    return SimpleNamespace(api=api, key=key, seen=seen)


def post_chat(service_api, *, query="查询数据", inputs=None, conversation_id=None):
    return service_api.api.client.post("/api/service/chat-messages", headers=headers(service_api.key),
        json={"user": USER, "query": query, "inputs": inputs or {}, "conversation_id": conversation_id})
