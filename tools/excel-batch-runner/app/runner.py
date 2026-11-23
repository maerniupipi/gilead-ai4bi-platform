"""One batch at a time, with a bounded shared worker queue."""
import asyncio
from collections import Counter
import time

from app.client import AgentClient, ExecutionError
from app.models import TERMINAL_ROWS, RowResult
from app.report import Report
from app.storage import SourceChangedError
from app.workbook import cell_output


class Runner:
    def __init__(self, storage, client=None):
        self.storage = storage
        self.client = client or AgentClient()
        self.task = None
        self.job = None
        self.rows = []
        self.stopping = False
        self._checkpoint_lock = asyncio.Lock()
        self.checkpoint_error = ""

    @property
    def active(self):
        return self.task is not None and not self.task.done()

    def start(self, source, rows, config, filename, source_path=None):
        if self.active:
            raise ValueError("已有批次正在执行，请等待完成或停止后再执行")
        if not any(row.status == "pending" for row in rows):
            raise ValueError("没有可执行问题，请检查 sheet、起始行和输出列覆盖选项")
        target = {"url": config.url, "app_id": config.app_id, "version_id": config.version_id}
        self.job = self.storage.create(source, rows, filename, source_path=source_path, target=target)
        self.rows = rows
        self.stopping = False
        self.checkpoint_error = ""
        self.task = asyncio.create_task(self._run(config.model_copy(deep=True)))
        return self.snapshot(self.job["job_id"])

    def stop(self, job_id):
        if not self.job or self.job["job_id"] != job_id or not self.active:
            raise ValueError("该任务当前未运行")
        self.stopping = True
        self.job["status"] = "stopping"
        self.storage.save_job(self.job)

    async def wait(self):
        if self.task is not None:
            await self.task

    def get(self, job_id):
        if self.job and self.job["job_id"] == job_id:
            return self.job, self.rows
        return self.storage.load(job_id, recover=True)

    def snapshot(self, job_id):
        job, rows = self.get(job_id)
        counts = dict(Counter(row.status for row in rows))
        completed = sum(row.status in TERMINAL_ROWS for row in rows)
        return {key: value for key, value in job.items() if key != "row_ids"} | {
            "counts": counts, "total": len(rows), "finished": completed,
            "overflow": sum(bool(row.export_warning) for row in rows),
            "result_file": job.get("source_path") or str((self.storage.job_dir(job_id) / "result.xlsx").resolve())}

    async def _checkpoint(self):
        async with self._checkpoint_lock:
            rows = [RowResult(**row.to_dict()) for row in self.rows]
            write = asyncio.create_task(asyncio.to_thread(
                self.storage.save_workbook, self.job["job_id"], rows))
            try:
                try:
                    await asyncio.shield(write)
                except asyncio.CancelledError:
                    # A thread cannot be cancelled: finish its atomic save before releasing the lock.
                    await write
                    raise
            except Exception as exc:
                self.stopping = True
                self.checkpoint_error = (str(exc) if isinstance(exc, SourceChangedError) else (
                    f"XLSX 保存失败（{type(exc).__name__}）；已停止派发，"
                    "已保存工作簿及行日志仍保留。请检查磁盘空间、权限、外部修改或文件是否被 Excel 占用。"))
                raise

    async def _run(self, config):
        queue = asyncio.Queue()
        for row in self.rows:
            if row.status == "pending":
                queue.put_nowait(row)

        async def worker():
            while not self.stopping:
                try:
                    row = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                start = time.monotonic()
                row.status = "running"
                report = Report()
                try:
                    self.storage.save_row(self.job["job_id"], row)

                    def on_frame(frame):
                        row.event_count += 1
                        self.storage.append_event(self.job["job_id"], row, frame, row.event_count)
                        report.add(frame, row.event_count)
                        report.update_row(row)
                        cell_output(row)

                    await self.client.execute(config, row, on_frame)
                    row.status = "success"
                except asyncio.CancelledError:
                    row.status, row.error = "interrupted", "本地任务已中断，远端执行状态未知"
                    raise
                except ExecutionError as exc:
                    row.status, row.error = "failed", str(exc)
                except Exception as exc:
                    row.status = "failed"
                    row.error = f"本地执行或保存失败（{type(exc).__name__}）"
                finally:
                    row.elapsed = round(time.monotonic() - start, 3)
                    report.update_row(row)
                    cell_output(row)
                    try:
                        self.storage.save_row(self.job["job_id"], row)
                        await self._checkpoint()
                    except Exception:
                        self.stopping = True
                        raise
                    finally:
                        queue.task_done()

        workers = []
        try:
            workers = [asyncio.create_task(worker()) for _ in range(config.concurrency)]
            results = await asyncio.gather(*workers, return_exceptions=True)
            failures = [result for result in results if isinstance(result, BaseException)]
            if failures:
                self.job["status"] = "failed"
                self.job["error"] = self.checkpoint_error or "任务保存失败；已保存结果和行日志仍保留"
            else:
                self.job["status"] = "stopped" if self.stopping else "completed"
        except asyncio.CancelledError:
            for task in workers:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            self.job["status"] = "interrupted"
            self.job["error"] = "本地任务已中断，远端执行状态未知"
        except Exception as exc:
            self.job["status"] = "failed"
            self.job["error"] = f"批次执行失败（{type(exc).__name__}）"
        finally:
            config.headers.clear()
            interrupted_rows = False
            for row in self.rows:
                if row.status in {"pending", "running"}:
                    was_running = row.status == "running"
                    row.status = "interrupted" if was_running else "cancelled"
                    row.error = "执行已停止或中断，未自动重发"
                    if was_running:
                        interrupted_rows = True
                        row.output += "\n\n[error] " + row.error
                    try:
                        self.storage.save_row(self.job["job_id"], row)
                    except OSError:
                        self.job["error"] = "部分任务状态保存失败；内存结果仍可下载"
            if interrupted_rows:
                try:
                    await self._checkpoint()
                except Exception:
                    self.job["status"] = "failed"
                    self.job["error"] = self.checkpoint_error
            try:
                self.storage.save_job(self.job)
            except OSError:
                self.job["status"] = "failed"
                self.job["error"] = "任务状态保存失败；内存结果仍可下载"
