"""Read-only management of nested sessions; all DB/model calls are isolated."""
import json
import time
from uuid import uuid4

import pytest

from app.models.chatbi import ChatBIAPIKey, ChatBIConversation, ChatBIConversationContext, ChatBIMessage, ChatBIMessageDiagnostic
from app.models.user import User
from app.routers.chatbi.conversations import router
from test_chatbi_credentials import api, ask, make_key, headers, ADMIN, USER, LEGACY_KEY

PATH = "/api/chatbi/conversations"


@pytest.fixture
def managed(api):
    api.client.app.include_router(router)
    return api


def listing(managed, **params):
    response = managed.client.get(PATH, headers=ADMIN, params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def detail(managed, cid, **params):
    response = managed.client.get(f"{PATH}/{cid}", headers=ADMIN, params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_sessions_are_grouped_by_key_and_contain_ordered_question_answers(managed):
    first_key, first_secret = make_key(managed)
    second_key, second_secret = make_key(managed)
    first = ask(managed, first_secret)
    ask(managed, first_secret, first["conversation_id"])
    other = ask(managed, second_secret)
    result = listing(managed)
    assert result["total"] == 2
    filtered = listing(managed, key_id=first_key["id"])
    assert filtered["total"] == 1
    assert filtered["items"][0]["message_count"] == 2
    assert filtered["items"][0]["user_id"] == "admin123"
    assert filtered["items"][0]["key_id"] == first_key["id"]
    assert listing(managed, key_id=second_key["id"])["items"][0]["id"] == other["conversation_id"]
    body = detail(managed, first["conversation_id"])
    assert [m["sequence"] for m in body["messages"]] == [1, 2]
    assert all(m["query"] == "上海销售额？" and m["answer"] == "模拟销售数据" for m in body["messages"])
    serialized = json.dumps(body)
    assert first_secret not in serialized and second_secret not in serialized and '"owner"' not in serialized and '"key_hash"' not in serialized


def test_message_pagination_does_not_skip_or_repeat_turns(managed):
    _, key = make_key(managed)
    first = ask(managed, key)
    for _ in range(2): ask(managed, key, first["conversation_id"])
    assert [m["sequence"] for m in detail(managed, first["conversation_id"], page=1, page_size=2)["messages"]] == [1, 2]
    last = detail(managed, first["conversation_id"], page=2, page_size=2)
    assert [m["sequence"] for m in last["messages"]] == [3]
    assert last["total"] == 3
    assert detail(managed, first["conversation_id"], page=5, page_size=2)["messages"] == []


def test_filters_search_answers_and_escape_like_characters(managed):
    row, key = make_key(managed)
    first, second = ask(managed, key), ask(managed, key)
    with managed.factory() as db:
        message = db.get(ChatBIMessage, first["message_id"])
        message.answer = "literal 50%_growth <img src=x onerror=alert(1)>"
        message.status = "failed"; message.error = "模拟失败"
        message.created_at = 100; message.finished_at = 120
        db.commit()
    assert listing(managed, user="admin123")["total"] == 2
    assert listing(managed, user="ADMIN123")["total"] == 2
    assert listing(managed, user="other")["total"] == 0
    assert listing(managed, keyword="50%_growth")["items"][0]["id"] == first["conversation_id"]
    assert listing(managed, keyword="50XXgrowth")["total"] == 0
    assert listing(managed, keyword="' OR 1=1 --")["total"] == 0
    assert listing(managed, keyword=second["conversation_id"])["total"] == 1
    assert listing(managed, status="failed")["items"][0]["id"] == first["conversation_id"]
    assert listing(managed, start_at=100, end_at=120)["total"] == 1
    assert listing(managed, start_at=121)["total"] == 1
    assert listing(managed, page_size=1)["items"][0]["id"] == second["conversation_id"]
    assert listing(managed, page=2, page_size=1)["items"][0]["id"] == first["conversation_id"]
    assert "<img" in detail(managed, first["conversation_id"])["messages"][0]["answer"]  # UI must escape, never execute stored HTML.


def test_keyword_finds_root_nested_and_lab_traces_in_any_turn_without_duplicate_sessions(managed):
    key_row, key = make_key(managed)
    other_key_row, other_key = make_key(managed)
    first = ask(managed, key)
    second = ask(managed, key, first['conversation_id'])
    ask(managed, other_key)
    root, nested, lab, old_invocation = [str(uuid4()) for _ in range(4)]
    with managed.factory() as db:
        first_diagnostic = db.get(ChatBIMessageDiagnostic, first['message_id'])
        first_diagnostic.traces = [{'trace_id': root, 'kind': 'workflow'}]
        diagnostic = db.get(ChatBIMessageDiagnostic, second['message_id'])
        diagnostic.traces = [{'trace_id': root, 'kind': 'workflow'},
                             {'trace_id': nested, 'kind': 'workflow', 'parent_trace_id': root},
                             {'trace_id': lab, 'kind': 'lab', 'parent_trace_id': nested}]
        diagnostic.invocations = [{'kind': 'lab', 'trace_id': old_invocation, 'inputs': {}}]
        db.commit()
    for trace_id in [root, nested, lab, old_invocation, lab.upper()]:
        result = listing(managed, keyword=' ' + trace_id + ' ')
        assert result['total'] == 1
        assert result['items'][0]['id'] == first['conversation_id']
        assert result['items'][0]['message_count'] == 2
    assert listing(managed, keyword=lab, key_id=key_row['id'])['total'] == 1
    assert listing(managed, keyword=lab, key_id=other_key_row['id'])['total'] == 0
    assert listing(managed, keyword=lab, user='another-user')['total'] == 0
    assert listing(managed, keyword=str(uuid4()))['total'] == 0


def test_historical_trace_search_works_before_and_after_incremental_indexing(managed):
    from sqlalchemy import update, delete
    from app.models.chatbi import ChatBITraceLookup, ChatBIDiagnosticIndexState
    from app.services.trace_index import backfill_trace_index
    _, key = make_key(managed)
    first = ask(managed, key)
    trace_id = str(uuid4())
    with managed.factory() as db:
        # Simulate a record created before the indexing listener was installed.
        db.execute(update(ChatBIMessageDiagnostic).where(ChatBIMessageDiagnostic.message_id == first['message_id']).values(
            traces=[{'trace_id': trace_id, 'kind': 'lab'}], updated_at=1))
        db.execute(delete(ChatBITraceLookup).where(ChatBITraceLookup.message_id == first['message_id']))
        db.execute(delete(ChatBIDiagnosticIndexState).where(ChatBIDiagnosticIndexState.message_id == first['message_id']))
        db.commit()
    assert listing(managed, keyword=trace_id)['total'] == 1
    assert backfill_trace_index(managed.factory) == 1
    assert backfill_trace_index(managed.factory) == 0
    assert listing(managed, keyword=trace_id)['total'] == 1
    with managed.factory() as db:
        assert db.get(ChatBITraceLookup, (trace_id, first['message_id'])) is not None


@pytest.mark.parametrize("status", ["running", "failed", "stopped"])
def test_all_terminal_and_running_turns_are_visible(managed, status):
    _, key = make_key(managed)
    first = ask(managed, key)
    ask(managed, key, first["conversation_id"])
    with managed.factory() as db:
        last = db.query(ChatBIMessage).filter_by(conversation_id=first["conversation_id"], sequence=2).one()
        last.status = status; last.answer = "部分回答"; last.error = "模拟说明" if status == "failed" else None
        db.commit()
    assert listing(managed, status=status)["total"] == 1
    result = detail(managed, first["conversation_id"])
    assert result["conversation"]["status"] == status
    assert result["messages"][1]["answer"] == "部分回答"
    assert result["total"] == 2


def test_historical_runtime_is_not_replaced_by_current_key_binding(managed):
    row, key = make_key(managed)
    first = ask(managed, key)
    managed.client.put(f"/api/chatbi/keys/{row['id']}", headers=ADMIN, json={"name": "新名称", "workflow_id": 1, "version_id": 12})
    result = detail(managed, first["conversation_id"])["conversation"]
    assert result["runtime"] == "agent:1:11:3" and result["key_name"] == "新名称"
    managed.client.patch(f"/api/chatbi/keys/{row['id']}/enabled", headers=ADMIN, json={"enabled": False})
    assert listing(managed, key_id=row["id"])["items"][0]["key_enabled"] is False








def test_unattributed_history_is_still_in_all_sessions(managed):
    make_key(managed)
    cid = str(uuid4())
    with managed.factory() as db:
        db.add(ChatBIConversation(id=cid, owner="0" * 64, runtime="autobi:1", created_at=int(time.time()) + 5))
        db.add(ChatBIMessage(id=str(uuid4()), task_id=str(uuid4()), owner="0" * 64, conversation_id=cid,
                            sequence=1, query="未知来源历史", answer="保留原文", status="succeeded"))
        db.commit()
    assert listing(managed)["total"] == 1
    item = listing(managed, key_id="unassigned")["items"][0]
    assert item["id"] == cid and item["key_id"] is None
    assert detail(managed, cid)["messages"][0]["answer"] == "保留原文"


def test_preview_is_bounded_without_changing_full_answer(managed):
    _, key = make_key(managed)
    first = ask(managed, key)
    with managed.factory() as db:
        msg = db.get(ChatBIMessage, first["message_id"])
        msg.answer = "完整答案" * 2000
        msg.content = [{"type": "chart", "title": "预览", "outputs": {"rows": [{"city": str(n)} for n in range(200)],
            "dimensions": [{"key": "city", "name": "城市"}], "series": []}},
            {"type": "table", "title": "宽表", "outputs": {"columns": [{"key": f"c{i}", "name": f"列{i}"} for i in range(80)],
                "rows": [{f"c{i}": i for i in range(80)}], "total_rows": 1}}]
        db.commit()
    message = detail(managed, first["conversation_id"])["messages"][0]
    assert len(message["answer"]) == 8000
    assert len(message["content"][0]["outputs"]["rows"]) == 50
    assert message["content"][0]["outputs"]["truncated"] is True
    assert len(message["content"][1]["outputs"]["columns"]) == 30
    assert len(message["content"][1]["outputs"]["rows"][0]) == 30


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 101}, {"key_id": "invalid"}, {"status": "bogus"}, {"start_at": 10, "end_at": 1}])
def test_invalid_filters_are_rejected(managed, params):
    response = managed.client.get(PATH, headers=ADMIN, params=params)
    assert response.status_code == 400


def test_details_use_existing_uuid_and_normal_platform_identity(managed):
    _, key = make_key(managed)
    first = ask(managed, key)
    assert managed.client.get(f"{PATH}/{uuid4()}", headers=ADMIN).status_code == 404
    assert managed.client.get(f"{PATH}/invalid", headers=ADMIN).status_code == 400
    managed.client.cookies.clear()
    for path in (PATH, f"{PATH}/{first['conversation_id']}"):
        assert managed.client.get(path, headers={**ADMIN, **headers(key)}).status_code == 200


def test_logged_in_member_can_read_without_second_management_session(managed):
    with managed.factory() as db:
        db.get(User, 1).system_role = "member"; db.commit()
    assert managed.client.get(PATH, headers=ADMIN).status_code == 200
    managed.client.cookies.clear()
    assert managed.client.get(PATH, headers=ADMIN).status_code == 200
