"""Generic caller ownership and customer-independent service boundaries."""
import pytest
from app.services.chatbi.config import APIError, identity
from app.services.autobi.lab_pipeline_runner import _runtime_prompt
from tests.test_chatbi_credentials import api, make_key, headers


@pytest.mark.parametrize("caller", ["actor-001", "analyst@example.test", "分析师-A", "region:team/user-01"])
def test_service_accepts_opaque_identifiers_without_an_employee_directory(api, caller):
    _, key = make_key(api)
    reply = api.client.post("/api/service/chat-messages", headers=headers(key),
        json={"user": caller, "query": "查询数据", "inputs": {"region": "east"}})
    assert reply.status_code == 200
    assert api.calls[-1]["user"].user_id == caller
    assert api.calls[-1]["user"].credential_id
    assert api.calls[-1]["user"].owner != identity(caller).owner


@pytest.mark.parametrize("caller", ["", "  ", "user\nforged", "user\x00bad", "x" * 321])
def test_invalid_caller_has_no_default_identity(caller):
    with pytest.raises(APIError):
        identity(caller)


def test_identity_namespace_is_collision_free_at_separator_boundaries():
    assert identity("a:b", "c").owner != identity("b", "c:a").owner
    assert identity("same-user", "key-A").owner != identity("same-user", "key-B").owner


def test_business_features_do_not_append_organization_rules_to_saved_prompts():
    assert _runtime_prompt("分析 {{department}}", {"department": "east", "scope": ["A", "B"]}) == "分析 east"


def test_only_platform_service_paths_are_registered(api):
    paths = set(api.client.app.openapi()["paths"])
    assert "/api/service/chat-messages" in paths
    assert all(path.startswith(("/api/service/", "/api/chatbi/keys", "/api/users")) for path in paths)
    assert not any("snapshots" in path or "permission" in path for path in paths)


@pytest.mark.parametrize("result,expected", [({"exports":{"sql":"SELECT id FROM scoped_records"}}, "SELECT id FROM scoped_records"), ({"exports":{}}, None)])
def test_sql_transform_hook_calls_selected_workflow_and_never_falls_back(monkeypatch, result, expected):
    import asyncio
    from app.services.agent_app import workflow_engine
    from app.services.autobi.lab_pipeline_runner import _dispatch_step
    seen = []
    async def run(db, **kwargs):
        seen.append(kwargs)
        return result
    monkeypatch.setattr(workflow_engine, "run_nested_agent_workflow", run)
    config = {"request":{"advanced_config":{"sql_permission_rewrite_config":{
        "enable":True, "target_app_id":8, "target_version_id":12}}}}
    features = {"user_id":"actor-001", "region":"east", "custom_scope":[1,2]}
    acc = {"generated_sql":"SELECT id FROM records"}
    async def invoke():
        return await _dispatch_step(None, 15, "query", config, 1, acc, {}, features)
    if expected is None:
        with pytest.raises(ValueError, match="未返回 SQL"):
            asyncio.run(invoke())
    else:
        _, output = asyncio.run(invoke())
        assert output["rewritten_sql"] == expected
        assert acc["generated_sql"] == expected
    assert seen[0]["agent_app_id"] == 8 and seen[0]["version_id"] == 12
    assert seen[0]["inputs"]["query"] == "SELECT id FROM records"
    assert seen[0]["inputs"]["features"] == features
