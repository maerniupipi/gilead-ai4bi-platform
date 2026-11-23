"""Immutable request snapshots and per-turn execution capture (never credential values)."""
from datetime import datetime
import json
import time
import traceback
from uuid import UUID, uuid4

from ...core.observability import bind_context, log_context, snapshot
from ...models.chatbi import ChatBIMessageDiagnostic
from ...core.invocation_capture import _capture, capture_invocation


def record_request(db, msg, body, user, runtime, original=None):
    normalized = body.model_dump(mode='json') if hasattr(body,'model_dump') else dict(body)
    db.add(ChatBIMessageDiagnostic(message_id=msg.id, request_id=log_context.get().get('request_id'),
        request=snapshot(original if original is not None else {'body':normalized,'source':'internal'}),
        execution=snapshot({'runtime':runtime,'user':{'user_id':user.user_id},
            'task_id':msg.task_id,'conversation_id':msg.conversation_id}),
        invocations=[], traces=[], updated_at=int(time.time()*1000)))


def begin_capture(message_id, conversation_id, task_id):
    bind_context(message_id=message_id,conversation_id=conversation_id,task_id=task_id,trace_id='')
    return _capture.set({'message_id':message_id,'invocations':[],'traces':[],'execution':{}})


def capture_execution(**values):
    capture = _capture.get()
    if capture is not None:
        capture['execution'].update(snapshot(values))


def record_trace(trace_id, payload=None, *, kind='workflow'):
    capture = _capture.get()
    if capture is None:
        return
    try:
        UUID(str(trace_id))
    except (ValueError,TypeError,AttributeError):
        return
    if not log_context.get().get('trace_id'):
        bind_context(trace_id=str(trace_id))
    payload = payload or {}
    item = snapshot({'trace_id':str(trace_id),'kind':kind,**{key:payload.get(key) for key in
        ('parent_trace_id','run_id','app_id','version_id','project_id','status','elapsed_ms','error') if payload.get(key) is not None}})
    previous = next((t for t in capture['traces'] if t['trace_id']==str(trace_id)),None)
    if previous is None:
        capture['traces'].append(item)
    else:
        if previous.get('kind') == 'lab' and not payload:
            item['kind'] = 'lab'
        previous.update(item)


def record_event(event):
    def visit(value, depth=0):
        if depth>8:
            return
        if isinstance(value,dict):
            for key,item in value.items():
                if key in {'trace_id','traceid','lab_trace_id','workflow_trace_id'} and isinstance(item,str):
                    record_trace(item,kind='lab' if key=='lab_trace_id' or event.get('type')=='lab_trace' else 'workflow')
                elif isinstance(item,(dict,list)):
                    visit(item,depth+1)
        elif isinstance(value,list):
            for item in value:
                visit(item,depth+1)
    if isinstance(event,dict):
        visit(event)


def persist_capture(db, message_id, **execution):
    capture = _capture.get()
    row = db.get(ChatBIMessageDiagnostic,message_id)
    if row is None:
        return
    if capture is not None:
        row.invocations = snapshot(capture['invocations'])
        row.traces = snapshot(capture['traces'])
        execution = {**capture['execution'],**execution}
    row.execution = {**(row.execution or {}),**snapshot(execution)}
    row.updated_at = int(time.time()*1000)


def end_capture(token):
    _capture.reset(token)


def diagnostic_view(row):
    if row is None:
        return None
    return snapshot({'request_id':row.request_id,'request':row.request,'execution':row.execution,
                     'invocations':row.invocations,'traces':row.traces,'updated_at':row.updated_at})
