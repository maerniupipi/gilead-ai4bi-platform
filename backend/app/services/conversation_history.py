"""Prompt context shared by ChatBI, nested agents and laboratory runs."""
from copy import deepcopy
from typing import Any, Mapping

HISTORY_CONTEXT_KEYS = frozenset({
    'history_question', 'history_messages', 'history', 'conversation_history',
})
HISTORY_QUESTION_ROUNDS = 5
NEW_QUESTION_TEXT = '当前是新问题'


def build_history_question(messages) -> str:
    questions = [message['content'].strip() for message in (messages or [])
                 if isinstance(message, dict) and message.get('role') == 'user'
                 and isinstance(message.get('content'), str) and message['content'].strip()]
    recent = questions[-HISTORY_QUESTION_ROUNDS:]
    return '\n'.join(f'{index}. {question}' for index, question in enumerate(recent, 1)) or NEW_QUESTION_TEXT


def history_context_values(inputs: Mapping[str, Any]) -> dict[str, Any]:
    values = {key: deepcopy(inputs[key]) for key in HISTORY_CONTEXT_KEYS if key in inputs}
    question = values.get('history_question')
    if not isinstance(question, str) or not question.strip():
        messages = values.get('history_messages')
        values['history_question'] = build_history_question(messages if isinstance(messages, list) else [])
    return values
