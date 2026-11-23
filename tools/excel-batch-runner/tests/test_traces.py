"""Offline trace aggregation, workbook protections and checkpoint regressions."""
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from openpyxl import load_workbook

from tests import OfflineCase, OfflineAsyncCase, workbook_bytes
from app.api import BatchService
from app.client import AgentClient
from app.models import RowResult, RunConfig, StartRequest
from app.report import Report
from app.sse import SSEFrame
from app.storage import Storage
from app.workbook import export_workbook, inspect_workbook, select_rows


def trace_frame(labs, workflow=None, end=False):
    features = {"lab_trace_ids": labs}
    if workflow:
        features["workflow_trace_id"] = workflow
    return SSEFrame(raw="", data="", payload={"data": {"messages": [
        {"type": "trace", "features": features}], "end": end}})


class TraceTests(OfflineCase):
    def test_all_labs_ordered_unique_and_separate_from_workflow(self):
        report = Report()
        report.add(trace_frame(["lab-1", "lab-2"], "root"), 1)
        report.add(trace_frame(["lab-1", "lab-nested", "stream", None, ""]), 2)
        report.add(trace_frame(["lab-failed"], end=True), 3)
        row = RowResult("市场", 2, "q", output_format="split_trace", status="failed", error="断流")
        report.update_row(row)
        self.assertEqual(row.lab_trace_ids, ["lab-1", "lab-2", "lab-nested", "lab-failed"])
        self.assertEqual(row.workflow_trace_ids, ["root"])
        self.assertIn("lab_trace_id: lab-nested", row.output)
        wb = load_workbook(io.BytesIO(export_workbook(workbook_bytes(), [row])))
        self.assertEqual(wb["市场"]["J1"].value, "实验室 TraceID")
        self.assertEqual(wb["市场"]["J2"].value, "lab-1\nlab-2\nlab-nested\nlab-failed")
        self.assertIn("未完成", wb["市场"]["I2"].value)
        wb.close()

    def test_only_explicit_trace_fields_are_collected(self):
        report = Report()
        report.add(SSEFrame(raw="", data="", payload={"data": {"labTraceIds": ["lab-body"], "messages": [
            {"type": "data_citations", "features": {"data_citations": [{"data": [{"trace_id": "business-data"}]}]}},
            {"type": "statistics", "features": {"lab_trace_id": "lab-stats", "workflowTraceId": "root"}}
        ]}}), 1)
        row = RowResult("市场", 2, "q")
        report.update_row(row)
        self.assertEqual(row.lab_trace_ids, ["lab-body", "lab-stats"])
        self.assertNotIn("business-data", row.lab_trace_ids)

    def test_j_content_and_merge_are_protected(self):
        wb = load_workbook(io.BytesIO(workbook_bytes()))
        wb["市场"]["J2"] = "已有数据"
        source = io.BytesIO(); wb.save(source)
        row = select_rows(source.getvalue(), ["市场"], output_format="split_trace")[0]
        self.assertEqual(row.status, "skipped")
        overview = next(sheet for sheet in inspect_workbook(source.getvalue()) if sheet["name"] == "市场")
        self.assertEqual(overview["existing"], 1)
        row = select_rows(source.getvalue(), ["市场"], overwrite=True, output_format="split_trace")[0]
        self.assertEqual(row.status, "pending")
        wb["市场"].merge_cells("J2:K2")
        source = io.BytesIO(); wb.save(source); wb.close()
        row = select_rows(source.getvalue(), ["市场"], overwrite=True, output_format="split_trace")[0]
        self.assertEqual(row.status, "invalid")

    def test_j_overflow_is_independent_and_formula_safe(self):
        row = RowResult("市场", 2, "q", status="success", output_format="split_trace", sql="SELECT 1", answer="ok",
                        lab_trace_ids=["😀" * 16384])
        wb = load_workbook(io.BytesIO(export_workbook(workbook_bytes(), [row])))
        self.assertIn("超限", wb["市场"]["J2"].value)
        self.assertEqual(wb["市场"]["H2"].value, "SELECT 1")
        self.assertEqual(wb["市场"]["I2"].value, "ok")
        self.assertEqual(len(row.lab_trace_ids[0]), 16384)
        wb.close()
        row.lab_trace_ids = ["=formula", "lab\x00id"]
        wb = load_workbook(io.BytesIO(export_workbook(workbook_bytes(), [row])))
        self.assertEqual(wb["市场"]["J2"].data_type, "s")
        self.assertEqual(wb["市场"]["J2"].value, "=formula\nlab\\u0000id")
        wb.close()

    def test_historical_tasks_leave_j_unchanged(self):
        wb = load_workbook(io.BytesIO(workbook_bytes()))
        wb["市场"]["J1"] = "原表头"; wb["市场"]["J2"] = "原有业务值"
        source = io.BytesIO(); wb.save(source); wb.close()
        for output_format in ["split", "trace"]:
            row = RowResult("市场", 2, "q", status="success", output_format=output_format, output="过程", answer="回答")
            wb = load_workbook(io.BytesIO(export_workbook(source.getvalue(), [row])))
            self.assertEqual(wb["市场"]["J2"].value, "原有业务值")
            self.assertEqual(wb["市场"]["J1"].value, "原表头")
            wb.close()

    def test_recovery_replays_trace_metadata_to_j(self):
        with TemporaryDirectory() as root:
            storage = Storage(Path(root))
            row = RowResult("市场", 2, "q", status="running", output_format="split_trace")
            job = storage.create(workbook_bytes(), [row], "test.xlsx")
            storage.append_event(job["job_id"], row, trace_frame(["before-crash"]), 1)
            _, rows = storage.load(job["job_id"], recover=True)
            self.assertEqual(rows[0].status, "interrupted")
            self.assertEqual(rows[0].lab_trace_ids, ["before-crash"])
            wb = load_workbook(io.BytesIO(storage.result(job["job_id"])))
            self.assertEqual(wb["市场"]["J2"].value, "before-crash")
            wb.close()


class TraceExecutionTests(OfflineAsyncCase):
    async def test_source_checkpoint_and_result_copy_keep_all_traces(self):
        frames = [trace_frame(["lab-first"], "root"), trace_frame(["lab-second", "lab-first"], end=True)]
        payload = "".join("data: " + json.dumps(frame.payload) + "\n\n" for frame in frames).encode()
        with TemporaryDirectory() as root:
            source = Path(root) / "input.xlsx"; source.write_bytes(workbook_bytes())
            client = AgentClient(httpx.MockTransport(lambda request: httpx.Response(200,
                headers={"Content-Type": "text/event-stream"}, content=payload)))
            service = BatchService(Path(root) / "jobs", client)
            opened = service.open_workbook(str(source))
            job = service.start(StartRequest(upload_id=opened["upload_id"], sheets=["市场"], config=RunConfig()))
            await service.runner.wait()
            for data in [source.read_bytes(), service.export(job["job_id"])]:
                wb = load_workbook(io.BytesIO(data))
                self.assertEqual(wb["市场"]["J2"].value, "lab-first\nlab-second")
                wb.close()
            detail = service.row(job["job_id"], service.runner.rows[0].row_id)
            self.assertEqual(detail["workflow_trace_ids"], ["root"])
            self.assertEqual(detail["lab_trace_ids"], ["lab-first", "lab-second"])
