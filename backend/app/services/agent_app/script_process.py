"""Supervise script processes and forward progress without blocking the API."""
import asyncio
import builtins
import os
import pickle
import signal
import struct
import sys
import threading
from pathlib import Path

from fastapi import HTTPException

_slots = threading.BoundedSemaphore(int(os.getenv("WORKFLOW_SCRIPT_CONCURRENCY", "4")))
_waiting = threading.BoundedSemaphore(int(os.getenv("WORKFLOW_SCRIPT_QUEUE_CAPACITY", "64")))


async def run_script(code, kwargs, legacy_values):
    if not _waiting.acquire(blocking=False):
        raise HTTPException(503, "脚本执行容量已满，请稍后再试")
    process = None
    acquired = False
    try:
        async with asyncio.timeout(float(os.getenv("WORKFLOW_SCRIPT_TIMEOUT_SECONDS", "120"))):
            while not _slots.acquire(blocking=False):
                await asyncio.sleep(0.02)
            acquired = True
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "app.services.agent_app.script_process",
                cwd=str(Path(__file__).resolve().parents[3]),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            values = {**legacy_values, "_thought_events": []}
            request = pickle.dumps((code, kwargs, values))
            process.stdin.write(struct.pack("!Q", len(request)) + request)
            await process.stdin.drain()
            process.stdin.close()
            while True:
                size = struct.unpack("!Q", await process.stdout.readexactly(8))[0]
                kind, value = pickle.loads(await process.stdout.readexactly(size))
                if kind == "thought":
                    legacy_values["_thought_events"].append(value)
                elif kind == "cache":
                    legacy_values["_legacy_cache"][value[0]] = value[1]
                elif kind == "error":
                    if value.get("status_code") is not None:
                        raise HTTPException(value["status_code"], value.get("detail"))
                    error_type = getattr(builtins, value["type"], RuntimeError)
                    if not isinstance(error_type, type) or not issubclass(error_type, Exception):
                        error_type = RuntimeError
                    raise error_type(value["message"])
                elif kind == "result":
                    return value
    except TimeoutError as exc:
        raise ValueError("工作流脚本排队或执行超时，已终止执行") from exc
    except asyncio.IncompleteReadError as exc:
        raise ValueError("工作流脚本进程提前退出") from exc
    finally:
        try:
            if process is not None:
                # Terminate the process group, including subprocesses created by
                # the script, on completion, cancellation and timeout.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await asyncio.shield(process.wait())
        finally:
            if acquired:
                _slots.release()
            _waiting.release()


def _worker():
    from types import SimpleNamespace
    from .executors.script import _run_restricted_script

    output = sys.stdout.buffer
    # Imported modules and scripts may print. Keep the IPC stream separate.
    sys.stdout = sys.stderr

    def send(kind, value):
        data = pickle.dumps((kind, value))
        output.write(struct.pack("!Q", len(data)) + data)
        output.flush()

    class Thoughts(list):
        def append(self, item):
            send("thought", item)

    class Cache(dict):
        def __init__(self, values):
            super().__init__(values)
            self.snapshots = {key: pickle.dumps(value) for key, value in self.items()}

        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            send("cache", (key, value))
            self.snapshots[key] = pickle.dumps(value)

        def flush_changes(self):
            # cache_get can return a list/dict that a legacy script mutates in
            # place. Publish only changed entries, preserving other branches.
            for key, value in self.items():
                if self.snapshots.get(key) != pickle.dumps(value):
                    send("cache", (key, value))

    try:
        size = struct.unpack("!Q", sys.stdin.buffer.read(8))[0]
        code, kwargs, values = pickle.loads(sys.stdin.buffer.read(size))
        values["_thought_events"] = Thoughts()
        values["_legacy_cache"] = Cache(values["_legacy_cache"])
        try:
            result = _run_restricted_script(code, kwargs, SimpleNamespace(**values))
        finally:
            values["_legacy_cache"].flush_changes()
        send("result", result)
    except BaseException as exc:
        send("error", {"type": type(exc).__name__, "message": str(exc),
                       "status_code": getattr(exc, "status_code", None),
                       "detail": getattr(exc, "detail", None)})


if __name__ == "__main__":
    _worker()
