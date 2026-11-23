"""Lifespan-scoped HTTP pools. Authentication stays on each request."""
import asyncio
from contextlib import asynccontextmanager
import weakref

import httpx

_clients = weakref.WeakKeyDictionary()


@asynccontextmanager
async def model_client(timeout):
    loop = asyncio.get_running_loop()
    clients = _clients.setdefault(loop, {})
    key = (httpx.AsyncClient, str(timeout))
    if key not in clients and len(clients) >= 16:
        async with httpx.AsyncClient(timeout=timeout) as client:
            yield client
        return
    if key not in clients:
        clients[key] = await httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=20),
        ).__aenter__()
    yield clients[key]


async def close_http_clients():
    clients = _clients.pop(asyncio.get_running_loop(), {})
    await asyncio.gather(*(client.aclose() for client in clients.values()), return_exceptions=True)
