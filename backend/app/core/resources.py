"""Bounded, thread-local SDK clients keyed by complete connection settings."""
import hashlib
import json
import threading
from collections import OrderedDict

import requests

_local = threading.local()
_all_resources = []
_lock = threading.Lock()


def thread_resource(factory, config):
    key = (factory, hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).digest())
    cache = getattr(_local, "resources", None)
    if cache is None:
        cache = _local.resources = OrderedDict()
        with _lock:
            _all_resources.append(cache)
    if key not in cache:
        cache[key] = factory(config)
    cache.move_to_end(key)
    while len(cache) > 16:
        _, old = cache.popitem(last=False)
        close = getattr(old, "close", None)
        if close:
            close()
    return cache[key]


def _requests_session(config):
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=1, max_retries=0)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def embedding_session():
    return thread_resource(_requests_session, {})


def close_thread_resources():
    cache = getattr(_local, "resources", None)
    if cache is None:
        return
    del _local.resources
    with _lock:
        _all_resources[:] = [registered for registered in _all_resources if registered is not cache]
    for resource in cache.values():
        close = getattr(resource, "close", None)
        if close:
            close()
    cache.clear()


def close_resources():
    with _lock:
        for cache in _all_resources:
            for resource in list(cache.values()):
                close = getattr(resource, "close", None)
                if close:
                    close()
            cache.clear()
        _all_resources.clear()
