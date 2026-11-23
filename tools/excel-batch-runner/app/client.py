"""Remote agent client; transports are injectable for fully offline tests."""
import asyncio

import httpx

from app.models import RowResult, RunConfig
from app.sse import SSEDecoder


class ExecutionError(Exception):
    """Safe message suitable for the page and persisted results."""


class AgentClient:
    def __init__(self, transport=None):
        self.transport = transport

    async def execute(self, config: RunConfig, row: RowResult, on_frame):
        payload = {
            "app_id": config.app_id, "version_id": config.version_id,
            "message": row.question, "conversation_id": row.conversation_id,
            "caller": config.caller, "stream": True,
            "inputs": {"input": row.question, "question": row.question, "channel": config.channel},
        }
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream",
                   **config.headers}
        timeout = httpx.Timeout(connect=config.connect_timeout, read=config.read_timeout,
                                write=config.connect_timeout, pool=config.connect_timeout)
        decoder = SSEDecoder()
        completed = False

        def consume(frames):
            nonlocal completed
            for frame in frames:
                on_frame(frame)
                if frame.parse_error:
                    raise ExecutionError(frame.parse_error)
                if frame.is_end:
                    completed = True
                    return True
            return False

        try:
            async with asyncio.timeout(config.total_timeout):
                async with httpx.AsyncClient(timeout=timeout, transport=self.transport,
                                             follow_redirects=False, trust_env=False) as client:
                    async with client.stream("POST", config.url, json=payload, headers=headers) as response:
                        if not 200 <= response.status_code < 300:
                            raise ExecutionError(f"HTTP {response.status_code}，未自动重试")
                        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                        if content_type != "text/event-stream":
                            raise ExecutionError("响应 Content-Type 不是 text/event-stream")
                        async for chunk in response.aiter_bytes():
                            if consume(decoder.feed(chunk)):
                                return
                        if consume(decoder.finish()):
                            return
                        raise ExecutionError("流已关闭，但尚未收到 data.end=true；结果不完整")
        except httpx.ReadTimeout:
            raise ExecutionError("流读取空闲超时，已保留已接收事件") from None
        except httpx.ConnectTimeout:
            raise ExecutionError("连接超时，未自动重试") from None
        except httpx.TimeoutException:
            raise ExecutionError("请求传输超时，未自动重试") from None
        except TimeoutError:
            raise ExecutionError("单行执行超过总时限，已保留已接收事件") from None
        except httpx.HTTPError:
            raise ExecutionError("网络或传输错误，未自动重试") from None
        except UnicodeError:
            raise ExecutionError("响应包含无效 UTF-8 数据") from None
        finally:
            if not completed:
                for frame in decoder.abort():
                    on_frame(frame)
