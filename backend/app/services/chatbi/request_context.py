"""Build trusted, customer-neutral service inputs and conversation history."""
from copy import deepcopy
import json
from ..conversation_history import build_history_question


def build_runtime_inputs(query, inputs, conversation_id, history, user, *, workflow=False):
    trusted = {**deepcopy(inputs), 'user': user.user_id, 'user_id': user.user_id,
               'conversation_id': conversation_id, 'history_messages': deepcopy(history),
               'history_question': build_history_question(history),
               'history': json.dumps(history, ensure_ascii=False),
               'conversation_history': json.dumps(history, ensure_ascii=False)}
    trusted['features'] = deepcopy(trusted)
    if workflow:
        trusted.update(question=query, input=query, user_message=query, message=query)
    return trusted
