import asyncio
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import httpx

from tests import OfflineAsyncCase, event_bytes, workbook_bytes
from app.models import RowResult, RunConfig
from app.workbook import select_rows

try:
    from app.client import AgentClient, ExecutionError
    from app.storage import Storage
    from app.runner import Runner
except ModuleNotFoundError:
    AgentClient = None


class MemoryStream(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks, self.delay = chunks, delay

    async def __aiter__(self):
        for chunk in self.chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


class ExecutionTests(OfflineAsyncCase):
    def setUp(self):
        super().setUp()
        self.assertIsNotNone(AgentClient, "Execution implementation is missing")
        parent = Path("runtime") / "offline-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="execution-", dir=parent))

    def client(self, chunks, status=200, delay=0, captured=None):
        def handle(request):
            if captured is not None:
                captured.append(json.loads(request.content))
            return httpx.Response(status, headers={"Content-Type": "text/event-stream"},
                                  stream=MemoryStream(chunks, delay))
        return AgentClient(transport=httpx.MockTransport(handle))

    async def test_payload_mapping_and_terminal_text_are_preserved(self):
        sent, frames = [], []
        row = RowResult("销售", 2, "你好")
        client = self.client([event_bytes(progress="正在执行", kind="progress"),
                              event_bytes(end=True, content="终帧回答")], captured=sent)
        await client.execute(RunConfig(), row, frames.append)
        self.assertEqual(sent[0]["message"], "你好")
        self.assertEqual(sent[0]["inputs"], {"input": "你好", "question": "你好", "channel": "api-docs"})
        self.assertEqual(sent[0]["conversation_id"], row.conversation_id)
        self.assertNotEqual(row.conversation_id, RowResult("销售", 3, "你好").conversation_id)
        self.assertIn("终帧回答", frames[-1].raw)
        self.assertTrue(frames[-1].is_end)

    async def test_premature_close_is_failure_with_partial_frames(self):
        frames = []
        with self.assertRaisesRegex(ExecutionError, "end=true"):
            await self.client([event_bytes(content="部分内容")]).execute(
                RunConfig(), RowResult("市场", 2, "q"), frames.append)
        self.assertEqual(len(frames), 1)

    async def test_partial_frame_survives_read_failure(self):
        frames = []
        partial = event_bytes(content="尚未结束的回答").rstrip(b"\n")
        with self.assertRaises(ExecutionError):
            await self.client([partial, httpx.ReadError("simulated")]).execute(
                RunConfig(), RowResult("市场", 2, "q"), frames.append)
        self.assertEqual(len(frames), 1)
        self.assertIn("尚未结束的回答", frames[0].raw)
        self.assertTrue(frames[0].partial)
        self.assertFalse(frames[0].is_end)

    async def test_partial_utf8_bytes_survive_timeout(self):
        frames = []
        partial = b'data: {"answer":"' + "你".encode("utf-8")[:2]
        with self.assertRaises(ExecutionError):
            await self.client([partial, httpx.ReadTimeout("simulated")]).execute(
                RunConfig(), RowResult("市场", 2, "q"), frames.append)
        self.assertEqual(len(frames), 1)
        self.assertIn("e4bd", frames[0].raw_bytes_hex)
        self.assertTrue(frames[0].partial)

    async def test_http_failure_does_not_expose_response_or_headers(self):
        with self.assertRaisesRegex(ExecutionError, "HTTP 401") as raised:
            await self.client([b"secret-response"], status=401).execute(
                RunConfig(headers={"Authorization": "secret-token"}),
                RowResult("市场", 2, "q"), lambda _: None)
        self.assertNotIn("secret", str(raised.exception))

    async def test_malformed_frame_is_saved_before_failure(self):
        frames = []
        with self.assertRaises(ExecutionError):
            await self.client([b"data: invalid-json\n\n"]).execute(
                RunConfig(), RowResult("市场", 2, "q"), frames.append)
        self.assertIn("invalid-json", frames[0].raw)

    async def test_total_and_read_timeout_are_distinguished(self):
        with self.assertRaisesRegex(ExecutionError, "总时限"):
            await self.client([event_bytes(end=True)], delay=.1).execute(
                RunConfig(total_timeout=.01), RowResult("市场", 2, "q"), lambda _: None)
        with self.assertRaisesRegex(ExecutionError, "读取"):
            await self.client([httpx.ReadTimeout("contains-secret")]).execute(
                RunConfig(), RowResult("市场", 2, "q"), lambda _: None)

    async def test_runner_respects_shared_concurrency_and_single_row_failure(self):
        from app.sse import SSEDecoder
        from openpyxl import load_workbook
        from io import BytesIO
        class Worker:
            active = peak = 0
            async def execute(self, config, row, callback):
                self.active += 1
                self.peak = max(self.peak, self.active)
                await asyncio.sleep(.01)
                self.active -= 1
                if row.row == 3:
                    raise ExecutionError("模拟失败")
                callback(SSEDecoder().feed(event_bytes(end=True, content=f"结果{row.row}"))[0])

        worker = Worker()
        storage = Storage(self.root)
        runner = Runner(storage, worker)
        rows = [RowResult("市场", i, str(i)) for i in range(2, 10)]
        job = runner.start(workbook_bytes(), rows, RunConfig(concurrency=3), "demo.xlsx")
        await runner.wait()
        self.assertEqual(worker.peak, 3)
        self.assertEqual([r.status for r in rows].count("failed"), 1)
        self.assertEqual([r.status for r in rows].count("success"), 7)
        self.assertEqual(runner.snapshot(job["job_id"])["status"], "completed")
        self.assertEqual(runner.snapshot(job["job_id"])["counts"]["failed"], 1)
        saved = load_workbook(BytesIO(storage.result(job["job_id"])))
        for number in range(2, 10):
            expected = "模拟失败" if number == 3 else f"结果{number}"
            self.assertIn(expected, saved["市场"].cell(number, 8).value)
        saved.close()

    async def test_stop_finishes_inflight_and_does_not_dispatch_pending(self):
        started, release = asyncio.Event(), asyncio.Event()
        class Worker:
            async def execute(self, config, row, callback):
                started.set()
                await release.wait()

        runner = Runner(Storage(self.root), Worker())
        rows = [RowResult("市场", i, "q") for i in range(2, 6)]
        job = runner.start(workbook_bytes(), rows, RunConfig(concurrency=1), "demo.xlsx")
        await started.wait()
        with self.assertRaises(ValueError):
            runner.start(workbook_bytes(), [], RunConfig(), "again.xlsx")
        runner.stop(job["job_id"])
        release.set()
        await runner.wait()
        self.assertEqual([r.status for r in rows], ["success", "cancelled", "cancelled", "cancelled"])
        self.assertEqual(runner.snapshot(job["job_id"])["status"], "stopped")

    async def test_storage_failure_terminates_job_instead_of_hanging(self):
        storage = Storage(self.root)
        runner = Runner(storage, self.client([event_bytes(end=True)]))
        rows = [RowResult("市场", 2, "q")]
        job = runner.start(workbook_bytes(), rows, RunConfig(), "demo.xlsx")
        with patch.object(storage, "append_event", side_effect=OSError("disk-secret")):
            await runner.wait()
        snapshot = runner.snapshot(job["job_id"])
        self.assertEqual(snapshot["counts"]["failed"], 1)
        self.assertNotEqual(snapshot["status"], "running")
        self.assertNotIn("disk-secret", json.dumps(snapshot))

    async def test_recovery_keeps_partial_logs_without_resending(self):
        storage = Storage(self.root)
        row = RowResult("市场", 2, "q", status="running")
        job = storage.create(workbook_bytes(), [row], "demo.xlsx")
        from app.sse import SSEDecoder
        frame = SSEDecoder().feed(event_bytes(content="重启前输出"))[0]
        storage.append_event(job["job_id"], row, frame, 1)
        restored_job, restored_rows = storage.load(job["job_id"], recover=True)
        self.assertEqual(restored_job["status"], "interrupted")
        self.assertEqual(restored_rows[0].status, "interrupted")
        self.assertIn("重启前输出", restored_rows[0].output)

    async def test_recovered_long_trace_has_consistent_overflow_flag(self):
        storage = Storage(self.root)
        row = RowResult("市场", 2, "q", status="running")
        job = storage.create(workbook_bytes(), [row], "demo.xlsx")
        from app.sse import SSEDecoder
        from app.workbook import export_workbook
        from openpyxl import load_workbook
        from io import BytesIO
        frame = SSEDecoder().feed(event_bytes(content="长" * 33000))[0]
        storage.append_event(job["job_id"], row, frame, 1)
        runner = Runner(storage)
        self.assertEqual(runner.snapshot(job["job_id"])["overflow"], 1)
        _, rows = runner.get(job["job_id"])
        self.assertTrue(rows[0].export_warning)
        workbook = load_workbook(BytesIO(export_workbook(workbook_bytes(), rows)))
        self.assertIn("超限", workbook["市场"]["H2"].value)
        workbook.close()

    async def test_each_finished_row_is_in_xlsx_before_next_question_finishes(self):
        second_started, release = asyncio.Event(), asyncio.Event()
        from app.sse import SSEDecoder
        from io import BytesIO
        from openpyxl import load_workbook
        class Worker:
            async def execute(self, config, row, callback):
                if row.sheet == "市场":
                    second_started.set()
                    await release.wait()
                callback(SSEDecoder().feed(event_bytes(end=True, content=row.sheet + "回答"))[0])

        storage = Storage(self.root)
        runner = Runner(storage, Worker())
        rows = select_rows(workbook_bytes(), ["销售", "市场"])
        job = runner.start(workbook_bytes(), rows, RunConfig(concurrency=1), "demo.xlsx")
        try:
            await asyncio.wait_for(second_started.wait(), 3)
            self.assertTrue(runner.active)
            result_path = storage.job_dir(job["job_id"]) / "result.xlsx"
            self.assertTrue(result_path.exists(), "Each row must be saved before the batch ends")
            saved = load_workbook(BytesIO(result_path.read_bytes()))
            self.assertIn("销售回答", saved["销售"]["H2"].value)
            self.assertIsNone(saved["市场"]["H2"].value)
            self.assertEqual(saved["销售"]["H4"].value, "旧结果")
            saved.close()
            original = load_workbook(BytesIO(storage.source(job["job_id"])))
            self.assertIsNone(original["销售"]["H2"].value)
            original.close()
        finally:
            release.set()
            await runner.wait()
        saved = load_workbook(BytesIO(result_path.read_bytes()))
        self.assertIn("市场回答", saved["市场"]["H2"].value)
        saved.close()

    async def test_atomic_workbook_failure_keeps_previous_file(self):
        storage = Storage(self.root)
        row = RowResult("市场", 2, "q", status="success", output="第一版")
        job = storage.create(workbook_bytes(), [row], "demo.xlsx")
        self.assertTrue(hasattr(storage, "save_workbook"), "Workbook checkpoint is missing")
        storage.save_workbook(job["job_id"], [row])
        path = storage.job_dir(job["job_id"]) / "result.xlsx"
        original = path.read_bytes()
        row.output = "第二版"
        with patch("app.storage.os.replace", side_effect=PermissionError("模拟文件占用")):
            with self.assertRaises(PermissionError):
                storage.save_workbook(job["job_id"], [row])
        self.assertEqual(path.read_bytes(), original)

    async def test_failed_checkpoint_stops_new_requests_but_keeps_row_log(self):
        storage = Storage(self.root)
        runner = Runner(storage, self.client([event_bytes(end=True, content="完成的回答")]))
        rows = [RowResult("市场", i, "q") for i in range(2, 5)]
        job = runner.start(workbook_bytes(), rows, RunConfig(concurrency=1), "demo.xlsx")
        self.assertTrue(hasattr(storage, "save_workbook"), "Workbook checkpoint is missing")
        with patch.object(storage, "save_workbook", side_effect=PermissionError("private-path")):
            await runner.wait()
        self.assertEqual([row.status for row in rows], ["success", "cancelled", "cancelled"])
        snapshot = runner.snapshot(job["job_id"])
        self.assertEqual(snapshot["status"], "failed")
        self.assertIn("XLSX", snapshot["error"])
        self.assertNotIn("private-path", snapshot["error"])
        _, saved_rows = storage.load(job["job_id"])
        self.assertIn("完成的回答", saved_rows[0].output)

    async def test_recovery_rebuilds_xlsx_from_already_saved_completed_row(self):
        from io import BytesIO
        from openpyxl import load_workbook
        storage = Storage(self.root)
        row = RowResult("市场", 2, "q")
        job = storage.create(workbook_bytes(), [row], "demo.xlsx")
        row.status, row.output = "success", "已完成但未更新工作簿"
        storage.save_row(job["job_id"], row)
        storage.load(job["job_id"], recover=True)
        path = storage.job_dir(job["job_id"]) / "result.xlsx"
        self.assertTrue(path.exists(), "Recovery must rebuild persisted Excel")
        workbook = load_workbook(BytesIO(path.read_bytes()))
        self.assertEqual(workbook["市场"]["H2"].value, "已完成但未更新工作簿")
        workbook.close()

    async def test_cancelling_during_checkpoint_finishes_atomic_write(self):
        import threading
        from io import BytesIO
        from openpyxl import load_workbook
        started, release = threading.Event(), threading.Event()
        class SlowStorage(Storage):
            def save_workbook(self, job_id, rows):
                started.set()
                if not release.wait(3):
                    raise RuntimeError("test writer was not released")
                return super().save_workbook(job_id, rows)

        storage = SlowStorage(self.root)
        runner = Runner(storage, self.client([event_bytes(end=True, content="中断前已完成")]))
        rows = [RowResult("市场", i, "q") for i in range(2, 4)]
        job = runner.start(workbook_bytes(), rows, RunConfig(concurrency=1), "demo.xlsx")
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 3))
            runner.task.cancel()
            await asyncio.sleep(0)
        finally:
            release.set()
            await runner.wait()
        self.assertEqual([row.status for row in rows], ["success", "cancelled"])
        self.assertEqual(runner.snapshot(job["job_id"])["status"], "interrupted")
        saved = load_workbook(BytesIO(storage.result(job["job_id"])))
        self.assertIn("中断前已完成", saved["市场"]["H2"].value)
        saved.close()

    async def test_compact_report_and_raw_frames_survive_run_and_recovery(self):
        from app.sse import SSEDecoder
        from io import BytesIO
        from openpyxl import load_workbook
        chunks = [event_bytes(content="第一段", unusual={"keep": 9}),
                  event_bytes(kind=["future"], content="数组类型"),
                  event_bytes(kind={"future": True}, content="对象类型"),
                  event_bytes(end=True, content="第二段")]
        storage = Storage(self.root)
        runner = Runner(storage, self.client(chunks))
        row = RowResult("市场", 2, "q")
        job = runner.start(workbook_bytes(), [row], RunConfig(), "demo.xlsx")
        await runner.wait()
        self.assertIn("【完整回答】\n第一段第二段", row.output)
        self.assertNotIn("raw:", row.output)
        records = [json.loads(line) for line in storage.events(job["job_id"], row.row_id).splitlines()]
        self.assertEqual(len(records), 4)
        self.assertIn("数组类型", row.output)
        self.assertIn("对象类型", row.output)
        for chunk, record in zip(chunks, records):
            self.assertEqual(record["raw"], chunk.decode().rstrip("\n"))
        saved = load_workbook(BytesIO(storage.result(job["job_id"])))
        self.assertEqual(saved["市场"]["H2"].value, row.output)
        saved.close()
        row2 = RowResult("市场", 2, "q", status="running")
        recovery_job = storage.create(workbook_bytes(), [row2], "interrupted.xlsx")
        for number, chunk in enumerate(chunks, 1):
            storage.append_event(recovery_job["job_id"], row2, SSEDecoder().feed(chunk)[0], number)
        _, recovered = storage.load(recovery_job["job_id"], recover=True)
        self.assertIn("【完整回答】\n第一段第二段", recovered[0].output)
        self.assertIn("状态: 已中断", recovered[0].output)
        self.assertIn('"keep": 9', recovered[0].output)

    async def test_cancelling_stream_saves_report_with_interrupted_status(self):
        from app.sse import SSEDecoder
        from io import BytesIO
        from openpyxl import load_workbook
        started = asyncio.Event()
        class Worker:
            async def execute(self, config, row, callback):
                callback(SSEDecoder().feed(event_bytes(content="部分回答"))[0])
                started.set()
                await asyncio.Event().wait()

        storage = Storage(self.root)
        runner = Runner(storage, Worker())
        row = RowResult("市场", 2, "q")
        job = runner.start(workbook_bytes(), [row], RunConfig(), "demo.xlsx")
        await asyncio.wait_for(started.wait(), 3)
        runner.task.cancel()
        await runner.wait()
        self.assertEqual(row.status, "interrupted")
        self.assertIn("状态: 已中断", row.output)
        self.assertIn("部分回答", row.output)
        saved = load_workbook(BytesIO(storage.result(job["job_id"])))
        self.assertEqual(saved["市场"]["H2"].value, row.output)
        saved.close()

    async def test_secrets_not_in_saved_state(self):
        storage = Storage(self.root)
        runner = Runner(storage, self.client([event_bytes(end=True, content="正常")]))
        config = RunConfig(headers={"Authorization": "TEST_SECRET_123"})
        job = runner.start(workbook_bytes(), select_rows(workbook_bytes(), ["市场"]),
                           config, "demo.xlsx")
        await runner.wait()
        for path in (self.root / "jobs" / job["job_id"]).rglob("*.json*"):
            self.assertNotIn("TEST_SECRET_123", path.read_text(encoding="utf-8"))
        self.assertEqual(config.headers["Authorization"], "TEST_SECRET_123")


if __name__ == "__main__":
    import unittest
    unittest.main()
