"""History comes from the caller's platform conversation, then crosses engine boundaries."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.chatbi import ChatBIConversation, ChatBIMessage, ChatBIMessageDiagnostic
from app.services.conversation_history import build_history_question, history_context_values, NEW_QUESTION_TEXT
from app.services.agent_app.workflow_run_ctx import substitute_llm_prompt, substitute_template
from tests.service_test_helpers import service_api, api, post_chat, events, context
from tests.test_chatbi_integration import factory, USER, OTHER
from app.schemas.chatbi import ChatRequest
from app.services.chatbi import chat


def test_question_window_preserves_repeated_questions_and_literal_braces():
    messages = [{'role':'user','content':question} for question in
                ['old 1','old 2','重复问题','重复问题','销售{{literal_user_id}}','多行\n问题','最后一问']]
    messages += [{'role':'assistant','content':'不加入答案'}, {'role':'user','content':'  '}]
    assert build_history_question(messages) == '1. 重复问题\n2. 重复问题\n3. 销售{{literal_user_id}}\n4. 多行\n问题\n5. 最后一问'
    assert build_history_question([]) == NEW_QUESTION_TEXT


def test_http_frontend_conversation_id_selects_latest_five_prior_questions(service_api):
    cid = None
    questions = [f'历史问题{i}' for i in range(1, 9)]
    for index, question in enumerate(questions):
        response = post_chat(service_api, query=question, conversation_id=cid)
        assert response.status_code == 200
        result = events(response)
        assert result[-1]['data']['status'] == 'succeeded'
        cid = result[0]['conversation_id']
        inputs = service_api.seen[-1]
        recent = questions[max(0,index-5):index]
        expected = '\n'.join(f'{number}. {value}' for number,value in enumerate(recent,1)) or NEW_QUESTION_TEXT
        assert inputs['history_question'] == inputs['features']['history_question'] == expected
        assert question not in inputs['history_question']
        assert substitute_llm_prompt(context(inputs), '历史：{{history_question}}') == '历史：' + expected
    with service_api.api.factory() as db:
        diagnostic = db.get(ChatBIMessageDiagnostic,result[0]['message_id'])
        assert diagnostic.request['body']['query'] == questions[-1]
        assert diagnostic.invocations[0]['inputs']['history_question'] == expected
    # Clearing the frontend conversation_id starts a separate context.
    fresh = post_chat(service_api, query='另一个会话的新问题', conversation_id='')
    assert events(fresh)[0]['conversation_id'] != cid
    assert service_api.seen[-1]['history_question'] == NEW_QUESTION_TEXT


def test_saved_history_is_bounded_and_excludes_other_owners_future_failed_and_stopped(factory):
    cid, other_cid = str(uuid4()), str(uuid4())
    def message(sequence, *, conversation=cid, owner=USER.owner, status='succeeded', query=None):
        return ChatBIMessage(id=str(uuid4()),task_id=str(uuid4()),conversation_id=conversation,
                             owner=owner,sequence=sequence,query=query or f'问题{sequence}',
                             answer=f'答案{sequence}',content=[],status=status)
    with factory() as db:
        db.add_all([ChatBIConversation(id=cid,owner=USER.owner,runtime='autobi:1',turn_count=30),
                    ChatBIConversation(id=other_cid,owner=USER.owner,runtime='autobi:1',turn_count=1)])
        db.add_all([message(number) for number in range(1,26)])
        db.add_all([message(26,status='failed'),message(27,status='stopped'),
                    message(28,owner=OTHER.owner,query='其他人的问题'),
                    message(29,status='running'),message(1,conversation=other_cid,query='其他会话的问题'),
                    message(99,query='本轮之后的问题')])
        db.commit()
        body = ChatRequest(user=USER.user,query='本次问题',conversation_id=cid)
        mid = chat.prepare_chat(db,body,USER)
    histories = []
    async def runner(db, runtime, query, inputs, conversation_id, history, user):
        histories.append(history)
        yield {'type':'text','content':'ok'}
    async def collect():
        return [chunk async for chunk in chat.stream_chat(mid,body,USER,factory=factory,runner=runner)]
    asyncio.run(collect())
    assert len(histories[0]) == 40
    assert histories[0][0] == {'role':'user','content':'问题6'}
    assert histories[0][-2] == {'role':'user','content':'问题25'}
    assert build_history_question(histories[0]) == '\n'.join(f'{index}. 问题{number}' for index,number in enumerate(range(21,26),1))


def test_nested_agent_and_lab_inherit_history_without_canvas_mappings(monkeypatch):
    from app.services.agent_app import workflow_engine
    from app.services.agent_app.executors import agent, lab
    inputs = history_context_values({'history_messages':[{'role':'user','content':'上海销售额'}]})
    inputs['input'] = '继续分析'
    seen = []
    monkeypatch.setattr(agent,'get_version_for_app',lambda *args:SimpleNamespace(id=2))
    async def nested(*args,**kwargs):
        seen.append(kwargs['inputs'])
        return {'output':'ok','exports':{}}
    monkeypatch.setattr(workflow_engine,'run_nested_agent_workflow',nested)
    node = {'data':{'agent_config':{'target_app_id':2,'target_version_id':2,'input_mapping':[
        {'target_field':'history_question','source_mode':'const','const_value':'旧画布默认值'},
        {'target_field':'features','source_mode':'const','const_value':{'business_month':'2026-11'}}]}}}
    asyncio.run(agent.execute(context(inputs),node))
    child = seen[0]
    assert child['history_question'] == child['features']['history_question'] == '1. 上海销售额'
    assert child['features']['business_month'] == '2026-11'
    child['history_messages'].append({'role':'user','content':'子流程数据'})
    assert len(inputs['history_messages']) == 1
    cfg = {'project_id':1,'input_mapping':[
        {'target_field':'content','source_mode':'const','const_value':'继续分析'},
        {'target_field':'features','source_mode':'const','const_value':{'history_question':'{{history_question}}'}}]}
    resolved = lab.resolve_lab_inputs(context(inputs),cfg)
    assert resolved['features']['history_question'] == '1. 上海销售额'


@pytest.mark.parametrize('history', [[], [{'role':'user','content':'上轮问题{{literal}}'}]])
def test_standalone_lab_and_prompt_templates_have_history_default_without_editing_saved_prompts(history):
    from app.services.autobi.lab_runtime import build_lab_run_spec_from_project_row
    row = {'id':1,'knowledge_base_id':1,'config_json':{'request':{'advanced_config':{
        'knowledge_rewrite_config':{'prompt':'历史：{{history_question}}；当前：{{input}}'},
        'nl2sql_config':{'prompt':'原有系统提示词，不含历史占位符'},
    }}}}
    original = deepcopy(row)
    expected = build_history_question(history)
    spec = build_lab_run_spec_from_project_row(row,content='本次问题',features={'history_messages':history})
    assert spec.features['history_question'] == expected
    adv = spec.lab_config['request']['advanced_config']
    assert adv['knowledge_rewrite_config']['prompt'] == '历史：' + expected + '；当前：{{input}}'
    assert adv['nl2sql_config']['prompt'] == original['config_json']['request']['advanced_config']['nl2sql_config']['prompt']
    assert row == original
    ctx = context(history_context_values({'history_messages':history}))
    assert substitute_template(ctx,'{{history_question}}') == expected
    assert substitute_llm_prompt(ctx,'{{history_question}}',{'history_question':{'source_mode':'const','const_value':''}}) == expected
    assert substitute_llm_prompt(context({}),'{{history_question}}') == NEW_QUESTION_TEXT


def test_frontend_multiturn_reaches_real_nested_workflow_and_model_request(api, monkeypatch):
    from app.models.agent_app import AgentAppVersion
    from app.services.chatbi import runtime
    from app.services.agent_app import workflow_engine
    from app.services.chat.service import ChatService
    from tests.test_chatbi_credentials import headers, make_key, USER as CALLER
    def node(key, kind, label, **config):
        return {'id':key,'data':{'kind':kind,'label':label,**config}}
    def graph(nodes):
        return {'nodes':nodes,'edges':[{'source':left['id'],'target':right['id']} for left,right in zip(nodes,nodes[1:])]}
    root = graph([node('s','start','开始'),node('i','userInput','输入'),
        node('a','agent','子智能体',agent_config={'target_app_id':2,'target_version_id':21,
            'input_mapping':[{'target_field':'input','source_mode':'ref','source_var':'输入.input'}]}),
        node('o','output','输出',output_config={'content_fields':[{'source_ref':'子智能体.output'}]})])
    child = graph([node('s','start','开始'),node('i','userInput','输入'),
        node('m','llm','模型',llm_config={'provider_id':1,'model_name':'isolated-model',
            'system_prompt':'固定系统提示词', 'use_user_prompt_template':True,
            'user_prompt':'历史：{{history_question}}\n当前：{{input}}'}),
        node('o','output','输出',output_config={'content_fields':[{'source_ref':'模型.text'}]})])
    with api.factory() as db:
        db.get(AgentAppVersion,11).workflow_json = deepcopy(root)
        db.get(AgentAppVersion,21).workflow_json = deepcopy(child)
        db.commit()
    requests = []
    async def send(db, request):
        requests.append(request)
        return SimpleNamespace(content=request.message)
    monkeypatch.setattr(chat,'run_analysis',runtime.run_analysis)
    monkeypatch.setattr(ChatService,'send_chat',send)
    monkeypatch.setattr(workflow_engine,'save_workflow_trace',lambda *args:None)
    monkeypatch.setattr(workflow_engine,'agent_run_trace_set',lambda *args:None)
    _, key = make_key(api)
    cid = None
    for number in range(1,8):
        response = api.client.post('/api/service/chat-messages',headers=headers(key),json={
            'user':CALLER,'query':f'问题{number}','inputs':{},'conversation_id':cid})
        frames = events(response)
        assert response.status_code == 200 and frames[-1]['data']['status'] == 'succeeded'
        cid = frames[0]['conversation_id']
        expected = '\n'.join(f'{index}. 问题{previous}' for index,previous in enumerate(range(max(1,number-5),number),1)) or NEW_QUESTION_TEXT
        assert requests[-1].system == '固定系统提示词'
        assert requests[-1].message == f'历史：{expected}\n当前：问题{number}'
    assert len(requests) == 7
    with api.factory() as db:
        assert db.get(AgentAppVersion,11).workflow_json == root
        assert db.get(AgentAppVersion,21).workflow_json == child
        diagnostic = db.get(ChatBIMessageDiagnostic,frames[0]['message_id'])
        child_call = next(call for call in diagnostic.invocations if call['kind'] == 'nested_agent')
        assert child_call['inputs']['history_question'] == expected
        assert child_call['inputs']['features']['history_question'] == expected
