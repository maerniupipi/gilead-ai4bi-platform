"""Coalesce progress snapshots while serializing writes for each trace."""
import asyncio
import copy
import logging
import weakref
from dataclasses import dataclass, field

from .execution import TRACE_WORK

logger = logging.getLogger(__name__)
_loops = weakref.WeakKeyDictionary()


def _terminal(payload):
    if "status" in payload:
        return payload["status"] in {"done", "error", "failed", "stopped", "succeeded"}
    states = [step.get("status") for step in payload.get("steps", [])]
    return bool(states) and (any(s in {"error", "failed", "stopped"} for s in states)
        or all(s in {"done", "success", "succeeded", "skipped"} for s in states))


@dataclass
class PendingTrace:
    payload: dict
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task = None


async def write_trace(writer, trace_id, payload):
    """The final snapshot is durable before the caller publishes completion.

    Progress retains every step in its latest snapshot. An in-flight write always
    finishes before a newer snapshot, including failures and cancellation.
    """
    loop = asyncio.get_running_loop()
    pending = _loops.setdefault(loop, {})
    key = (writer, trace_id)
    terminal = _terminal(payload)
    # Keep only the latest progress reference. Freeze it immediately before
    # handing it to the worker, which never observes subsequent mutations.
    snapshot = dict(payload)
    state = pending.get(key)
    if state is None:
        if len(pending) >= 256:
            # Bound buffered traces without dropping terminal records.
            await asyncio.shield(next(iter(pending.values())).task)
        state = PendingTrace(snapshot)
        pending[key] = state

        async def drain():
            try:
                while state.payload is not None:
                    try:
                        await asyncio.wait_for(state.wake.wait(), 0.25)
                    except TimeoutError:
                        pass
                    state.wake.clear()
                    current, state.payload = copy.deepcopy(state.payload), None
                    await TRACE_WORK.run(writer, trace_id, current)
            finally:
                pending.pop(key, None)

        state.task = asyncio.create_task(drain())
        def report(done):
            if not done.cancelled() and done.exception() is not None:
                logger.error("trace persistence failed trace_id=%s", trace_id,
                             exc_info=done.exception())
        state.task.add_done_callback(report)
    else:
        state.payload = snapshot
    if terminal:
        state.wake.set()
        await asyncio.shield(state.task)


async def flush_traces():
    pending = _loops.get(asyncio.get_running_loop(), {})
    tasks = []
    for state in list(pending.values()):
        state.wake.set()
        tasks.append(state.task)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
