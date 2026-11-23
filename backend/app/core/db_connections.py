"""Bounded reusable pools for external business databases."""
import hashlib
import json
import threading
from collections import OrderedDict

from sqlalchemy.pool import QueuePool

_pools = OrderedDict()
_lock = threading.Lock()


def borrow_connection(purpose, settings, connect):
    key = (purpose, hashlib.sha256(json.dumps(settings, sort_keys=True, default=str).encode()).digest())
    with _lock:
        if key not in _pools:
            _pools[key] = QueuePool(connect, pool_size=2, max_overflow=1,
                                   timeout=5, recycle=300, reset_on_return="rollback")
        pool = _pools[key]
        _pools.move_to_end(key)
        while len(_pools) > 16:
            _, old = _pools.popitem(last=False)
            old.dispose()
    # Connecting and waiting for a slot happen outside the registry lock.
    return pool.connect()


def close_connection_pools():
    with _lock:
        for pool in _pools.values():
            pool.dispose()
        _pools.clear()
