"""HTTP-level auth and durable history tests; all agent traffic stays in memory."""
import io
import json
from pathlib import Path
import tempfile
from urllib.parse import quote
from zipfile import ZipFile

import httpx
from openpyxl import load_workbook
from sqlalchemy import select, update

from app.api import BatchService, create_app
from app.auth import COOKIE_NAME
from app.client import AgentClient
from app.database import accounts, jobs, sessions
from app.models import RowResult
from app.settings import Settings
from tests import OfflineAsyncCase, event_bytes, workbook_bytes
from tests.test_execution import MemoryStream


class AuthHistoryTests(OfflineAsyncCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.password = "test-credential-for-suite"
        self.app = create_app(self.root, Settings(admin_password=self.password))
        self.addCleanup(self.app.state.database.engine.dispose)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://localhost")
        self.addAsyncCleanup(self.client.aclose)
        self.app.state.service.runner.client = AgentClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"content-type": "text/event-stream"},
                stream=MemoryStream([event_bytes(end=True, content="数据库保存的完整回答")]))))

    async def login(self):
        response = await self.client.post("/api/auth/login", headers={"X-Local-Request": "1"},
            json={"username": "admin", "password": self.password})
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers.update({"X-Local-Request": "1", "X-CSRF-Token": response.json()["csrf"]})
        return response

    async def run_job(self):
        uploaded = await self.client.post("/api/uploads", headers={"X-Filename": quote("评测.xlsx")}, content=workbook_bytes())
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        response = await self.client.post("/api/jobs", json={"upload_id": uploaded.json()["upload_id"], "sheets": ["市场"]})
        self.assertEqual(response.status_code, 200, response.text)
        await self.app.state.service.runner.wait()
        return response.json()["job_id"]

    async def test_all_data_and_downloads_require_login(self):
        for path in ("/api/defaults", "/api/jobs", "/api/history", "/api/auth/me",
                     "/api/jobs/" + "a" * 32 + "/export", "/api/jobs/" + "a" * 32 + "/logs",
                     "/api/jobs/" + "a" * 32 + "/source"):
            self.assertEqual((await self.client.get(path)).status_code, 401, path)
        self.assertEqual((await self.client.post("/api/uploads", content=b"bad")).status_code, 401)
        self.assertEqual((await self.client.get("/")).headers["location"], "/login")
        self.assertEqual((await self.client.get("/healthz")).json(), {"status": "ok"})

    async def test_credentials_csrf_and_logout_revocation(self):
        bad = await self.client.post("/api/auth/login", headers={"X-Local-Request": "1"},
            json={"username": "admin", "password": "wrong"})
        self.assertEqual(bad.status_code, 401)
        response = await self.login()
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=lax", response.headers["set-cookie"])
        with self.app.state.database.engine.connect() as connection:
            saved = connection.execute(select(accounts.c.password_hash)).scalar_one()
            token_hash = connection.execute(select(sessions.c.token_hash)).scalar_one()
        self.assertTrue(saved.startswith("scrypt$"))
        self.assertNotIn(self.password, saved)
        token = self.client.cookies.get(COOKIE_NAME)
        self.assertNotEqual(token_hash, token)
        self.assertEqual((await self.client.post("/api/preview", headers={"X-CSRF-Token": "wrong"}, json={})).status_code, 403)
        self.assertEqual((await self.client.post("/api/auth/logout", headers={"Origin": "https://other.invalid"}, json={})).status_code, 403)
        self.assertEqual((await self.client.post("/api/workbooks/open", json={"path": "/etc/test.xlsx"})).status_code, 403)
        self.assertEqual((await self.client.post("/api/auth/logout", json={})).status_code, 200)
        self.client.cookies.set(COOKIE_NAME, token)
        self.assertEqual((await self.client.get("/api/history")).status_code, 401)

    async def test_bad_logins_are_throttled_and_expired_sessions_rejected(self):
        await self.login()
        with self.app.state.database.engine.begin() as connection:
            connection.execute(update(sessions).values(expires_at=0))
        self.assertEqual((await self.client.get("/api/auth/me")).status_code, 401)
        for _ in range(10):
            response = await self.client.post("/api/auth/login", headers={"X-Local-Request": "1"},
                json={"username": "unknown", "password": "wrong"})
            self.assertEqual(response.status_code, 401)
        self.assertEqual((await self.client.post("/api/auth/login", headers={"X-Local-Request": "1"},
            json={"username": "admin", "password": self.password})).status_code, 429)

    async def test_history_search_archive_download_and_restart(self):
        await self.login()
        job_id = await self.run_job()
        result = await self.client.get("/api/history")
        item = result.json()["items"][0]
        self.assertEqual(item["counts"], {"success": 1})
        self.assertEqual(item["target"]["app_id"], 1)
        self.assertEqual(item["target"]["version_id"], 1)
        self.assertEqual((await self.client.patch("/api/jobs/" + job_id, json={"title": "评测 100%_甲"})).status_code, 200)
        self.assertEqual((await self.client.get("/api/history", params={"query": "%_"})).json()["total"], 1)
        self.assertEqual((await self.client.get("/api/history", params={"query": "' OR 1=1 --"})).json()["total"], 0)
        self.assertEqual((await self.client.patch("/api/jobs/" + job_id, json={"archived": True})).status_code, 200)
        self.assertEqual((await self.client.get("/api/history")).json()["total"], 0)
        self.assertEqual((await self.client.get("/api/history?archived=true")).json()["total"], 1)
        output = await self.client.get("/api/jobs/" + job_id + "/export")
        self.assertEqual(output.status_code, 200)
        workbook = load_workbook(io.BytesIO(output.content))
        self.assertEqual(workbook["市场"]["I2"].value, "数据库保存的完整回答")
        workbook.close()
        source = await self.client.get("/api/jobs/" + job_id + "/source")
        original = load_workbook(io.BytesIO(source.content))
        self.assertEqual(original["市场"]["G2"].value, "市场情况")
        self.assertIsNone(original["市场"]["I2"].value)
        original.close()
        logs = await self.client.get("/api/jobs/" + job_id + "/logs")
        with ZipFile(io.BytesIO(logs.content)) as archive:
            content = json.loads(archive.read("results.json"))
            self.assertEqual(content["rows"][0]["answer"], "数据库保存的完整回答")
        # A new app reads the database and accepts the original persisted session.
        other = create_app(self.root, Settings())
        self.addCleanup(other.state.database.engine.dispose)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=other), base_url="http://localhost",
                                    cookies=self.client.cookies) as reopened:
            response = await reopened.get("/api/jobs/" + job_id)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["title"], "评测 100%_甲")
            self.assertTrue(response.json()["archived"])
            self.assertIsNone(other.state.service.runner.task)
        await self.client.patch("/api/jobs/" + job_id, json={"archived": False})
        self.assertEqual((await self.client.get("/api/history")).json()["total"], 1)

    async def test_database_recovers_interrupted_batch_without_replay(self):
        row = RowResult(sheet="市场", row=2, question="问题", status="running")
        job = self.app.state.service.storage.create(workbook_bytes(), [row], "unfinished.xlsx")
        restored = BatchService(self.root, database=self.app.state.database)
        snapshot = restored.runner.snapshot(job["job_id"])
        self.assertEqual(snapshot["status"], "interrupted")
        self.assertEqual(snapshot["counts"], {"interrupted": 1})
        self.assertIsNone(restored.runner.task)

    async def test_invalid_upload_and_history_changes_do_not_touch_database(self):
        await self.login()
        self.assertEqual((await self.client.post("/api/uploads", headers={"X-Filename": "bad.xlsx"}, content=b"bad")).status_code, 400)
        self.assertEqual((await self.client.get("/api/history?limit=101")).status_code, 422)
        self.assertEqual((await self.client.patch("/api/jobs/" + "a" * 32, json={"title": " "})).status_code, 400)
        self.assertEqual((await self.client.patch("/api/jobs/" + "a" * 32, json={"title": "test"})).status_code, 404)
        self.assertEqual((await self.client.get("/api/history")).json()["total"], 0)
