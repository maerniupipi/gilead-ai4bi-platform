"""Disable thinking at every model HTTP boundary, including saved enabled settings."""
from collections.abc import Mapping
from typing import Any


def _disabled_payload(payload, parameter):
    result = dict(payload)
    kwargs = dict(result.get('chat_template_kwargs') or {})
    for key in ('enable_thinking', 'reasoning_effort', 'thinking_budget'):
        result.pop(key, None)
        kwargs.pop(key, None)
    if parameter == 'enable_thinking':
        result['enable_thinking'] = False
        kwargs['enable_thinking'] = False
    else:
        result['reasoning_effort'] = 'none'
    if kwargs:
        result['chat_template_kwargs'] = kwargs
    else:
        result.pop('chat_template_kwargs', None)
    return result


def non_thinking_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Default OpenAI-compatible protocol: reasoning_effort=none."""
    return _disabled_payload(payload, 'reasoning_effort')


def model_thinking_payload(payload: Mapping[str, Any], provider: Any) -> dict[str, Any]:
    settings = getattr(provider, 'model_settings', None) or {}
    config = settings.get(payload.get('model')) or {}
    if hasattr(config, 'model_dump'):
        config = config.model_dump()
    # Only the provider's parameter dialect is retained. Enabled/effort/budget
    # values from historical settings or callers cannot enable thinking.
    parameter = config.get('parameter', 'reasoning_effort')
    if parameter in {'enable_thinking', 'thinking_budget'}:
        return _disabled_payload(payload, 'enable_thinking')
    return non_thinking_payload(payload)
