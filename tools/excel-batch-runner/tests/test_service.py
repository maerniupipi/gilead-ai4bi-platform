import io
import json
from pathlib import Path
import tempfile
from zipfile import ZipFile

from openpyxl import load_workbook

from tests import OfflineAsyncCase, workbook_bytes, event_bytes
from tests.test_execution import MemoryStream
from app.models import RunConfig, StartRequest, Selection
from app.client import AgentClient
import httpx

try:
    from app.api import BatchService, create_app
except ModuleNotFoundError:
    BatchService = None


class ServiceTests(OfflineAsyncCase):
    def setUp(self):
        super().setUp()
        self.assertIsNotNone(BatchService, "Service implementation is missing")
        parent = Path("runtime") / "offline-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="service-", dir=parent))
        self.service = BatchService(self.root, AgentClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"content-type": "text/event-stream"},
                                           stream=MemoryStream([event_bytes(end=True, content="完整结果")])))))

    async def test_upload_preview_run_and_export_directly_without_http(self):
        uploaded = self.service.upload("样例.xlsx", workbook_bytes(), 2)
        selected = Selection(upload_id=uploaded["upload_id"], sheets=["销售", "市场"])
        preview = self.service.preview(selected)
        self.assertEqual(preview["counts"], {"pending": 2, "skipped": 1})
        request = StartRequest(**selected.model_dump(), config=RunConfig(concurrency=2))
        job = self.service.start(request)
        await self.service.runner.wait()
        result = self.service.rows(job["job_id"], status="success")
        self.assertEqual(result["total"], 2)
        self.assertNotIn("output", result["items"][0])
        detail = self.service.row(job["job_id"], result["items"][0]["row_id"])
        self.assertIn("完整结果", detail["output"])
        output = load_workbook(io.BytesIO(self.service.export(job["job_id"])))
        self.assertIn("完整结果", output["销售"]["I2"].value)
        self.assertEqual(output["销售"]["H4"].value, "旧结果")
        output.close()
        with ZipFile(io.BytesIO(self.service.logs(job["job_id"]))) as archive:
            self.assertIn("results.json", archive.namelist())
            saved = json.loads(archive.read("results.json"))
            self.assertEqual(len(saved["rows"]), 3)
            self.assertTrue(any(name.endswith(".jsonl") for name in archive.namelist()))

    async def test_original_path_is_updated_without_download_and_backup_is_intact(self):
        path = (self.root / "original.xlsx").resolve()
        source = workbook_bytes()
        path.write_bytes(source)
        opened = self.service.open_workbook(str(path))
        self.assertEqual(opened["source_path"], str(path))
        job = self.service.start(StartRequest(upload_id=opened["upload_id"], sheets=["市场"]))
        await self.service.runner.wait()
        wb = load_workbook(path)
        self.assertEqual(wb["市场"]["H2"].value, "[未返回 SQL]")
        self.assertEqual(wb["市场"]["I2"].value, "完整结果")
        self.assertEqual(wb["销售"]["H4"].value, "旧结果")
        wb.close()
        self.assertEqual(self.service.storage.source(job["job_id"]), source)
        self.assertEqual(self.service.runner.snapshot(job["job_id"])["result_file"], str(path))
        self.assertEqual(self.service.runner.rows[0].output_format, "split_trace")

    async def test_changed_original_is_rejected_before_any_task_starts(self):
        path = (self.root / "changed.xlsx").resolve()
        path.write_bytes(workbook_bytes())
        opened = self.service.open_workbook(str(path))
        changed = workbook_bytes() + b"changed"
        path.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "变化"):
            self.service.start(StartRequest(upload_id=opened["upload_id"], sheets=["市场"]))
        self.assertIsNone(self.service.runner.task)
        self.assertEqual(path.read_bytes(), changed)
        with self.assertRaises(ValueError):
            self.service.open_workbook("relative.xlsx")

    async def test_external_change_during_execution_is_not_overwritten(self):
        path = (self.root / "external.xlsx").resolve()
        path.write_bytes(workbook_bytes())
        opened = self.service.open_workbook(str(path))
        job = self.service.start(StartRequest(upload_id=opened["upload_id"], sheets=["市场"]))
        changed = workbook_bytes() + b"external-change"
        path.write_bytes(changed)
        await self.service.runner.wait()
        self.assertEqual(path.read_bytes(), changed)
        self.assertEqual(self.service.runner.snapshot(job["job_id"])["status"], "failed")
        self.assertIn("外部修改", self.service.runner.snapshot(job["job_id"])["error"])
        self.service.export(job["job_id"])
        self.assertEqual(path.read_bytes(), changed, "Downloading a copy must not retry source write")

    async def test_selection_filters_pagination_and_path_validation(self):
        uploaded = self.service.upload("sample.xlsx", workbook_bytes(), 2)
        job = self.service.start(StartRequest(upload_id=uploaded["upload_id"], sheets=["销售", "市场"]))
        await self.service.runner.wait()
        result = self.service.rows(job["job_id"], sheet="市场", query="市场")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["row"], 2)
        result = self.service.rows(job["job_id"], offset=1, limit=1)
        self.assertEqual(len(result["items"]), 1)
        with self.assertRaises(ValueError):
            self.service.preview(Selection(upload_id="../outside", sheets=["销售"]))
        with self.assertRaises(ValueError):
            self.service.upload("../escape.xlsx", workbook_bytes(), 2)
        with self.assertRaises(ValueError):
            self.service.upload("wrong.csv", workbook_bytes(), 2)
        with self.assertRaises(ValueError):
            self.service.upload("bad.xlsx", b"not-a-workbook", 2)

    async def test_running_job_can_download_last_saved_xlsx(self):
        uploaded = self.service.upload("sample.xlsx", workbook_bytes(), 2)
        job = self.service.start(StartRequest(upload_id=uploaded["upload_id"], sheets=["市场"]))
        try:
            output = load_workbook(io.BytesIO(self.service.export(job["job_id"])))
            self.assertIsNone(output["市场"]["H2"].value)
            output.close()
        finally:
            await self.service.runner.wait()
        output = load_workbook(io.BytesIO(self.service.export(job["job_id"])))
        self.assertIn("完整结果", output["市场"]["I2"].value)
        output.close()

    async def test_reopen_completed_job_does_not_execute_again(self):
        uploaded = self.service.upload("sample.xlsx", workbook_bytes(), 2)
        job = self.service.start(StartRequest(upload_id=uploaded["upload_id"], sheets=["市场"]))
        await self.service.runner.wait()
        reopened = BatchService(self.root)
        self.assertEqual(reopened.runner.snapshot(job["job_id"])["counts"]["success"], 1)
        self.assertEqual(reopened.history()[0]["job_id"], job["job_id"])
        self.assertIsNone(reopened.runner.task)

    async def test_route_registration_matches_page_contract_without_requests(self):
        app = create_app(self.root)
        self.addCleanup(app.state.database.engine.dispose)
        paths = {route.path for route in app.routes}
        self.assertTrue({"/", "/api/defaults", "/api/uploads", "/api/preview",
                         "/api/jobs", "/api/jobs/{job_id}", "/api/jobs/{job_id}/rows",
                         "/api/jobs/{job_id}/rows/{row_id}", "/api/jobs/{job_id}/stop",
                         "/api/jobs/{job_id}/export", "/api/jobs/{job_id}/logs"} <= paths)


if __name__ == "__main__":
    import unittest
    unittest.main()
