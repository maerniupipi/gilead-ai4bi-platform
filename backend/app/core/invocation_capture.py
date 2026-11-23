"""Optional per-execution evidence shared by platform engines and adapters.

No dependency on platform client, HTTP routes or conversation database models. Adapters
decide when to start a capture and how to persist the collected evidence.
"""
from contextvars import ContextVar
import time
from uuid import uuid4

from .observability import snapshot

_capture = ContextVar('platform_execution_capture', default=None)


def capture_invocation(kind, inputs, **metadata):
    capture = _capture.get()
    if capture is not None:
        capture['invocations'].append(snapshot({
            'id': str(uuid4()), 'kind': kind, 'created_at': int(time.time() * 1000),
            'inputs': inputs, **metadata,
        }))
