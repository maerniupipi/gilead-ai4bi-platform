"""Exercise extensible inputs through HTTP and the real runtime parameter assembly."""
import json
from types import SimpleNamespace

import pytest

from app.services.chatbi import chat, runtime
from app.services.chatbi.config import APIError, validate_inputs
from tests.test_chatbi_credentials import api, headers, make_key, USER


BUSINESS_INPUTS = {
    "current_user_info": "caller@example.test",
    "portal_conversation_id": "client-probe-66603",
    "business_month": "2026-10", "limit": 12, "ratio": 0.75,
    "include_detail": False, "regions": ["上海", "北京"],
    "filters": {"region": "华东", "user_id": "business-record-id"}, "optional_value": None,
}


@pytest.mark.parametrize("allowed", [None, "[]"])
def test_business_inputs_reach_workflow_and_features_on_first_and_followup(api, monkeypatch, allowed):
    from app.services.agent_app import workflow_engine
    from app.repositories.agent_app import repository
    if allowed is None:
        monkeypatch.delenv("CHATBI_ALLOWED_INPUTS", raising=False)
    else:
        monkeypatch.setenv("CHATBI_ALLOWED_INPUTS", allowed)
    calls = []

    async def engine(db, app_id, version_id, inputs, **kwargs):
        calls.append(inputs)
        yield {"status": "done", "output": "参数传递成功"}

    monkeypatch.setattr(chat, "run_analysis", runtime.run_analysis)
    monkeypatch.setattr(workflow_engine, "run_agent_workflow_stream", engine)
    monkeypatch.setattr(repository, "get_version_for_app", lambda *args: SimpleNamespace(id=11, status="published", workflow_rev=3))
    _, key = make_key(api)
    body = {"user": USER, "query": "上海和北京的销售分别是多少？", "inputs": BUSINESS_INPUTS,
            "response_mode": "streaming", "conversation_id": "", "auto_generate_name": False}
    first = api.client.post("/api/service/chat-messages", headers=headers(key), json=body)
    assert first.status_code == 200, first.text
    events = [json.loads(line[6:]) for line in first.text.splitlines() if line.startswith("data: ")]
    assert events[-1]["data"]["status"] == "succeeded"
    cid = events[0]["conversation_id"]
    followup = api.client.post("/api/service/chat-messages", headers=headers(key), json={**body, "query": "继续分析", "conversation_id": cid})
    assert followup.status_code == 200, followup.text
    assert len(calls) == 2
    for inputs in calls:
        for name, value in BUSINESS_INPUTS.items():
            assert inputs[name] == inputs["features"][name] == value
        assert inputs["user_id"] == inputs["features"]["user_id"] == "admin123"
        assert inputs["user"] == inputs["features"]["user"] == USER
        assert inputs["conversation_id"] == inputs["features"]["conversation_id"] == cid
    assert calls[0]["input"] == body["query"]
    assert calls[1]["history_messages"] == [
        {"role": "user", "content": body["query"]}, {"role": "assistant", "content": "参数传递成功"}]


def test_business_inputs_also_reach_lab_features(api, monkeypatch):
    from app.services.autobi import lab_runtime
    monkeypatch.delenv("CHATBI_ALLOWED_INPUTS", raising=False)
    seen = []

    def build(db, project_id, *, content, features):
        seen.append(features)
        return SimpleNamespace(lab_config={})

    async def stream(*args, **kwargs):
        yield {"type": "summary", "delta": "实验室参数传递成功"}
        yield {"type": "done"}

    monkeypatch.setattr(chat, "run_analysis", runtime.run_analysis)
    monkeypatch.setattr(lab_runtime, "build_lab_run_spec_from_project_id", build)
    monkeypatch.setattr(lab_runtime, "stream_lab_native_sse", stream)
    response = api.client.post("/api/service/chat-messages", headers=headers("app-uat-" + "l" * 43),
                               json={"user": USER, "query": "销售", "inputs": BUSINESS_INPUTS})
    assert response.status_code == 200, response.text
    assert len(seen) == 1
    for key, value in BUSINESS_INPUTS.items():
        assert seen[0][key] == seen[0]["features"][key] == value


@pytest.mark.parametrize("name", ["user", "user_id", "features", "conversation_id", "history",
    "history_messages", "conversation_history", "history_question", "question", "input", "user_message", "message",
    "workflow_id", "workflow", "app_id", "agent_app_id", "version_id", "workflow_version", "runtime"])
def test_reserved_fields_still_rejected_without_whitelist(api, monkeypatch, name):
    monkeypatch.delenv("CHATBI_ALLOWED_INPUTS", raising=False)
    _, key = make_key(api)
    response = api.client.post("/api/service/chat-messages", headers=headers(key),
                               json={"user": USER, "query": "销售", "inputs": {name: "forged"}})
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_inputs"
    assert api.calls == []


def test_explicit_nonempty_allowlist_remains_an_opt_in_restriction(monkeypatch):
    monkeypatch.setenv("CHATBI_ALLOWED_INPUTS", '["business_month", "user_id"]')
    validate_inputs({"business_month": "2026-10"})
    for inputs in ({"new_parameter": True}, {"user_id": "forged"}):
        with pytest.raises(APIError) as caught:
            validate_inputs(inputs)
        assert caught.value.status == 400


@pytest.mark.parametrize("raw", ["invalid", "null", "{}", '[1]'])
def test_invalid_allowlist_reports_deployment_error(monkeypatch, raw):
    monkeypatch.setenv("CHATBI_ALLOWED_INPUTS", raw)
    with pytest.raises(APIError) as caught:
        validate_inputs({})
    assert caught.value.status == 503


@pytest.mark.parametrize("inputs", [None, [], "text", 1])
def test_inputs_must_remain_an_object(api, inputs):
    _, key = make_key(api)
    response = api.client.post("/api/service/chat-messages", headers=headers(key), json={"user": USER, "query": "销售", "inputs": inputs})
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_param"
