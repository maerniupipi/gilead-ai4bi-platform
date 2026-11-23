"""Orchestration must retain original failures instead of asking models to retry."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app.services.agent_app import ai_creator_service as creator
from app.schemas.agent_app import AiChatRequest
from app.services.xlsx_qa import qa_pipeline as qa, insight_pipeline as insight


def sheet():
    return qa.SheetInfo(1, 'sample.xlsx', 'sample', 't', [{'name':'amount','type':'number'}], '')


def test_excel_failed_sql_keeps_first_error_and_calls_model_once(monkeypatch):
    calls = {'model':0, 'sql':0}
    async def model(*args, **kwargs):
        calls['model'] += 1
        return {'sql':'SELECT missing FROM t'}
    def execute(*args, **kwargs):
        calls['sql'] += 1
        raise RuntimeError('original missing column')
    monkeypatch.setattr(qa.llm_client, 'chat_json', model)
    monkeypatch.setattr(qa, 'run_select', execute)
    state = {'id':'q1', 'question':'total'}
    asyncio.run(qa._process_subq(choice=None, bundle=qa.prompts.DEFAULT_PROMPTS,
        s=state, relevant_sheets=[sheet()], engine=None, all_allowed_tables=['t'],
        sql_max_rows=100, sql_timeout_ms=1000))
    assert calls == {'model':1, 'sql':1}
    assert state['sql_status'] == 'error' and 'original missing column' in state['error']
    assert state['sql'] == 'SELECT missing FROM t'


@pytest.mark.parametrize('tool_step', [False, True])
def test_creator_does_not_repair_invalid_json_but_keeps_normal_tool_steps(monkeypatch, tool_step):
    requests, tools = [], []
    async def model(*args, **kwargs):
        requests.append(kwargs)
        if tool_step and len(requests) == 1:
            return {'tool_calls':[{'id':'1','type':'function','function':{'name':'lookup','arguments':'{}'}}]}
        return {'content':'not JSON'}
    monkeypatch.setattr(creator.ChatService, 'chat_completion_openai', model)
    monkeypatch.setattr(creator.AiCreatorToolExecutor, 'run',
                        lambda self, name, args: tools.append(name) or {'items':[]})
    req = AiChatRequest(session_id='test-session', phase='WELCOME',
                        creator_model={'provider_id':1, 'model_name':'test'})
    result = asyncio.run(creator.run_ai_creator_chat(None, req))
    assert len(requests) == (2 if tool_step else 1)
    assert tools == (['lookup'] if tool_step else [])
    assert result.parse_error and result.content == '模型未返回合法 JSON。'


def test_insight_evidence_failure_does_not_generate_or_execute_another_sql(monkeypatch):
    calls = {'model':0, 'sql':0}
    dimensions = [{'id':'d1', 'title':'total', 'target_sheet_id':1,
                   'questions':[{'id':'q1','type':'overview','text':'total'}]}]
    async def model(*args, **kwargs):
        calls['model'] += 1
        return {'dimensions':dimensions} if calls['model'] == 1 else {'sql':'SELECT missing FROM t'}
    def execute(*args, **kwargs):
        calls['sql'] += 1
        raise RuntimeError('original missing column')
    monkeypatch.setattr(insight, 'ROLE_DEFINITIONS', [])
    monkeypatch.setattr(insight, 'profile_sheet', lambda *args: {})
    monkeypatch.setattr(insight, '_normalize_dimensions', lambda raw, sheets: raw)
    monkeypatch.setattr(insight.llm_client, 'resolve_llm', lambda *args, **kwargs: None)
    monkeypatch.setattr(insight.llm_client, 'chat_json', model)
    monkeypatch.setattr(insight, 'run_select', execute)
    monkeypatch.setattr(insight.XlsxQaRepository, 'create_or_reset_insight_report', lambda *args, **kwargs: None)
    monkeypatch.setattr(insight.XlsxQaRepository, 'update_insight_report', lambda *args, **kwargs: None)
    ctx = insight.InsightContext(db=SimpleNamespace(commit=lambda:None, rollback=lambda:None),
        engine=None, module_id=1, module_name='sample', active_sheets=[sheet()],
        module_understanding_md='', llm_provider_id=1, llm_model='test')
    async def run():
        stream = insight.run_insight_pipeline(ctx)
        try:
            async for chunk in stream:
                if chunk.startswith('event: query_result\n'):
                    return json.loads(chunk.split('data: ', 1)[1])
        finally:
            await stream.aclose()
    result = asyncio.run(run())
    assert calls == {'model':2, 'sql':1}  # planner + first SQL generation
    assert result['supported'] is False and 'original missing column' in result['error']
