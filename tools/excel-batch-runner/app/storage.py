"""Task-local persistence. No credentials or full request configuration are saved."""
from datetime import datetime, timezone
import json
import hashlib
import tempfile
import os
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4

from app.models import RowResult
from app.sse import SSEFrame
from app.report import Report
from app.workbook import cell_output, export_workbook


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("无效任务或记录 ID")
    return value


def write_json(path: Path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class SourceChangedError(OSError):
    """The selected workbook no longer matches a known checkpoint."""


class Storage:
    def __init__(self, root, database=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._workbook_lock = RLock()
        self.database = database
        if database:
            self._import_history()

    def _import_history(self):
        """Import legacy file history once; the database remains the source of truth."""
        for path in (self.root / "jobs").glob("*/job.json"):
            job = json.loads(path.read_text(encoding="utf-8"))
            if self.database.load(job["job_id"]) is None:
                results = [RowResult(**json.loads((path.parent / "rows" / (safe_id(row_id) + ".json")).read_text(
                    encoding="utf-8"))) for row_id in job["row_ids"]]
                self.database.create_job(job, results)

    def job_dir(self, job_id):
        return self.root / "jobs" / safe_id(job_id)

    def create(self, source: bytes, rows: list[RowResult], filename: str, source_path=None, target=None) -> dict:
        if source_path and Path(source_path).read_bytes() != source:
            raise ValueError("原始工作簿在加载后发生变化，请重新加载并预览")
        job_id = uuid4().hex
        directory = self.job_dir(job_id)
        (directory / "rows").mkdir(parents=True)
        (directory / "events").mkdir()
        (directory / "source.xlsx").write_bytes(source)
        self._write_workbook(job_id, source)
        if source_path:
            write_json(directory / "writeback.json", {"path": str(source_path),
                       "sha256": hashlib.sha256(source).hexdigest(), "pending_sha256": None})
        job = {"job_id": job_id, "filename": filename, "status": "running",
               "created_at": datetime.now(timezone.utc).isoformat(),
               "row_ids": [row.row_id for row in rows], "error": "",
               "source_path": str(source_path) if source_path else None, "target": target or {}}
        for row in rows:
            write_json(directory / "rows" / (safe_id(row.row_id) + ".json"), row.to_dict())
        write_json(directory / "job.json", job)
        if self.database:
            self.database.create_job(job, rows)
        return job

    def save_job(self, job):
        write_json(self.job_dir(job["job_id"]) / "job.json", job)
        if self.database:
            self.database.save_job(job)

    def save_row(self, job_id, row):
        write_json(self.job_dir(job_id) / "rows" / (safe_id(row.row_id) + ".json"),
                   row.to_dict())
        if self.database:
            self.database.save_row(job_id, row)

    def append_event(self, job_id, row, frame, number):
        record = {"number": number, "row_id": row.row_id, "sheet": row.sheet,
                  "row": row.row, "conversation_id": row.conversation_id, **frame.to_dict()}
        path = self.job_dir(job_id) / "events" / (safe_id(row.row_id) + ".jsonl")
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()

    def source(self, job_id):
        return (self.job_dir(job_id) / "source.xlsx").read_bytes()

    def _write_workbook(self, job_id, content):
        path = self.job_dir(job_id) / "result.xlsx"
        temporary = path.with_suffix(".xlsx.tmp")
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def _write_source(self, job_id, content):
        state_path = self.job_dir(job_id) / "writeback.json"
        if not state_path.exists():
            return
        state = json.loads(state_path.read_text(encoding="utf-8"))
        target = Path(state["path"])
        expected = {state["sha256"], state.get("pending_sha256")}
        def check():
            current = hashlib.sha256(target.read_bytes()).hexdigest()
            if current not in expected:
                raise SourceChangedError("原始工作簿被外部修改，已停止回写；请重新加载文件")
            return current

        current = check()
        digest = hashlib.sha256(content).hexdigest()
        if current == digest:
            write_json(state_path, {**state, "sha256": digest, "pending_sha256": None})
            return
        # Keep failed temporary files for diagnosis; never delete user files or backups.
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".batch-" + job_id + "-",
                                         suffix=".xlsx", dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        check()
        write_json(state_path, {**state, "pending_sha256": digest})
        check()
        os.replace(temporary, target)
        write_json(state_path, {**state, "sha256": digest, "pending_sha256": None})

    def save_workbook(self, job_id, rows, write_source=True):
        """Serialize XLSX writes; only replace the last good file once fully saved."""
        with self._workbook_lock:
            content = export_workbook(self.source(job_id), rows)
            self._write_workbook(job_id, content)
            if write_source:
                self._write_source(job_id, content)

    def result(self, job_id):
        with self._workbook_lock:
            return (self.job_dir(job_id) / "result.xlsx").read_bytes()

    def events(self, job_id, row_id):
        path = self.job_dir(job_id) / "events" / (safe_id(row_id) + ".jsonl")
        return path.read_bytes() if path.exists() else b""

    def load(self, job_id, recover=False):
        with self._workbook_lock:
            return self._load(job_id, recover)

    def _load(self, job_id, recover=False):
        directory = self.job_dir(job_id)
        saved = self.database.load(job_id) if self.database else None
        if self.database and saved is None:
            raise FileNotFoundError()
        if saved:
            job, values = saved
            rows = [RowResult(**value) for value in values]
        else:
            job = json.loads((directory / "job.json").read_text(encoding="utf-8"))
            rows = [RowResult(**json.loads(
                (directory / "rows" / (safe_id(row_id) + ".json")).read_text(encoding="utf-8")))
                for row_id in job["row_ids"]]
        if recover and job["status"] in {"running", "stopping"}:
            job["status"] = "interrupted"
            job["error"] = "服务已重启；未自动重发请求"
            for row in rows:
                if row.status not in {"pending", "running"}:
                    continue
                records = self.events(job_id, row.row_id).decode("utf-8").splitlines()
                report = Report()
                for record in records:
                    try:
                        item = json.loads(record)
                        frame = SSEFrame(**{key: item[key] for key in (
                            "raw", "data", "event", "event_id", "payload", "parse_error",
                            "partial", "raw_bytes_hex") if key in item})
                        report.add(frame, item["number"])
                    except (ValueError, KeyError, TypeError):
                        report.extra.append("[error] 部分事件日志损坏，原始日志仍保留")
                row.event_count = len(records)
                row.status = "interrupted" if records or row.status == "running" else "cancelled"
                row.error = "服务中断，未自动重发；远端执行状态未知"
                if records:
                    report.update_row(row)
                elif row.status == "interrupted":
                    row.output += ("\n\n" if row.output else "") + "[error] " + row.error
                cell_output(row)
                self.save_row(job_id, row)
            try:
                self.save_workbook(job_id, rows)
            except Exception as exc:
                job["error"] += f"；XLSX 恢复保存失败（{type(exc).__name__}），已保留行日志"
            self.save_job(job)
        return job, rows

    def list_jobs(self):
        if self.database:
            return self.database.list_jobs(limit=1000)["items"]
        result = []
        jobs_path = self.root / "jobs"
        if not jobs_path.exists():
            return result
        for path in jobs_path.glob("*/job.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                result.append({key: item[key] for key in (
                    "job_id", "filename", "status", "created_at")})
            except (OSError, ValueError, KeyError):
                continue
        return sorted(result, key=lambda item: item["created_at"], reverse=True)
