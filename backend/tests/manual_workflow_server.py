"""Local browser fixture: real workflow engine/executors, in-memory surrounding APIs.

Run from backend: .venv/bin/python -m tests.manual_workflow_server
Only binds 127.0.0.1:18001. No production app, database or Redis lifespan is loaded.
Login: workflow-review / review-local. App/version IDs: 9001 / 9001.
"""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

from app.services.agent_app import workflow_engine


APP_ID = VERSION_ID = 9001
SPACE = {"id": 9001, "name": "工作流本地验收", "role": "owner", "is_current": True}
SCRIPT_CODE = """def main(text: str, count: int, enabled: bool, offset: int):
    total = offset
    for value in range(count):
        total += 1
    print('total', total)
    return {'result': f'{text} | total={total} | enabled={enabled}', 'total': total}
"""
INITIAL_GRAPH = {
    "nodes": [
        {"id": "wf-start", "type": "wfCard", "position": {"x": 60, "y": 180},
         "data": {"kind": "start", "label": "开始"}},
        {"id": "wf-user-input", "type": "wfCard", "position": {"x": 380, "y": 180},
         "data": {"kind": "userInput", "label": "用户输入", "fields": [
             {"variable": "input", "display": "测试内容", "type": "string", "required": True,
              "source_mode": "ref", "source_ref": ["input", "input"], "default": "工作流验收"}
         ]}},
        {"id": "wf-script", "type": "wfCard", "position": {"x": 700, "y": 180},
         "data": {"kind": "script", "label": "脚本处理", "script_config": {
             "code": SCRIPT_CODE,
             "input_vars": [
                 {"name": "text", "type": "string", "source_mode": "ref", "ref": "用户输入.input"},
                 {"name": "count", "type": "number", "source_mode": "const", "const_value": "2"},
                 {"name": "enabled", "type": "boolean", "source_mode": "const", "const_value": False},
                 {"name": "offset", "type": "number", "source_mode": "const", "const_value": 0},
             ],
             "output_vars": [{"name": "result", "type": "string"}, {"name": "total", "type": "number"}],
         }}},
        {"id": "wf-output", "type": "wfCard", "position": {"x": 1020, "y": 180},
         "data": {"kind": "output", "label": "输出", "output_config": {
             "content_fields": [{"output_format": "text", "source_mode": "ref", "source_ref": "脚本处理.result"}],
             "metadata_fields": [{"name": "total", "type": "number", "source_mode": "ref", "source_ref": "脚本处理.total"}],
         }}},
    ],
    "edges": [{"id": f"e-{i}", "source": source, "target": target, "type": "wfPlus"}
              for i, (source, target) in enumerate([
                  ("wf-start", "wf-user-input"), ("wf-user-input", "wf-script"), ("wf-script", "wf-output")])],
}
GRAPH = deepcopy(INITIAL_GRAPH)
REVISION = 0
UNDO_STACK = None
TRACES = {}


def ok(data=None):
    return {"code": "SUCCESS", "message": "本地隔离验收环境", "data": data}


def version_data():
    return {"id": VERSION_ID, "app_id": APP_ID, "name": "本地验收版本", "status": "designing",
            "is_output": True, "workflow_rev": REVISION, "created_at": "2026-10-20T09:00:00"}


def app_data():
    return {"id": APP_ID, "name": "工作流逐节点验收", "description": "真实工作流执行器，本地内存数据",
            "space_id": SPACE["id"], "owner": "workflow-review", "versions": [version_data()],
            "output_version_id": VERSION_ID, "created_at": "2026-10-20T09:00:00"}


def get_version(db, app_id, version_id):
    if (app_id, version_id) != (APP_ID, VERSION_ID):
        return None
    return SimpleNamespace(**version_data(), workflow_json=deepcopy(GRAPH))


def save_trace(trace_id, payload):
    TRACES[trace_id] = deepcopy(payload)


class MemoryDB:
    def query(self, *args):
        return self

    def filter(self, *args):
        return self

    def first(self):
        return SimpleNamespace(name=app_data()["name"])


# Replace only persistence/lookup boundaries. Executors and graph execution stay real.
workflow_engine.get_version_for_app = get_version
workflow_engine.save_workflow_trace = save_trace
workflow_engine.agent_run_trace_set = save_trace
workflow_engine.agent_run_trace_get = lambda run_id: TRACES.get(run_id)
app = FastAPI(title="Workflow local acceptance fixture")


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({"code": "BAD_REQUEST", "message": str(exc), "data": None}, status_code=400)


@app.post("/api/users/login")
async def login(request: Request):
    data = await request.json()
    if data.get("username") != "workflow-review" or data.get("password") != "review-local":
        return JSONResponse({"code": "UNAUTHORIZED", "message": "请使用本地验收账号", "data": None}, status_code=401)
    return ok({"id": 9001, "username": "workflow-review", "display_name": "工作流验收", "system_role": "super_admin"})


@app.get("/api/spaces/current")
async def current_space():
    return ok(SPACE)


@app.get("/api/spaces")
async def spaces():
    return ok({"spaces": [SPACE], "current_space_id": SPACE["id"]})


@app.get("/api/agent_apps")
async def apps():
    return ok([app_data()])


@app.get("/api/agent_apps/folders")
@app.get("/api/model-providers")
@app.get("/api/knowledge_base")
@app.get("/api/data_sources")
@app.get("/api/data-sources")
async def empty_list():
    return ok([])


@app.get("/api/agent_apps/{app_id}/versions/{version_id}/workflow")
async def workflow(app_id: int, version_id: int):
    return ok({"workflow": GRAPH, "workflow_rev": REVISION, "undo_stack": UNDO_STACK})


@app.put("/api/agent_apps/{app_id}/versions/{version_id}/workflow")
async def save_workflow(app_id: int, version_id: int, request: Request):
    global GRAPH, REVISION, UNDO_STACK
    data = await request.json()
    if data.get("expected_rev") != REVISION:
        return JSONResponse({"code": "DUPLICATE", "message": "工作流版本已变更", "data": None}, status_code=409)
    GRAPH = {"nodes": data.get("nodes", []), "edges": data.get("edges", [])}
    UNDO_STACK = data.get("undo_stack")
    REVISION += 1
    return ok({"workflow": GRAPH, "workflow_rev": REVISION, "undo_stack": UNDO_STACK})


@app.get("/api/agent_apps/{app_id}/versions/{version_id}/params")
async def params(app_id: int, version_id: int):
    return ok({"input_params": [{"name": "input", "type": "STRING", "required": True}], "output_params": []})


@app.post("/api/agent_apps/{app_id}/versions/{version_id}/run")
async def run_workflow(app_id: int, version_id: int, request: Request):
    data = await request.json()
    return ok(await workflow_engine.run_agent_workflow(
        MemoryDB(), agent_app_id=app_id, version_id=version_id, inputs=data.get("inputs", {})))


@app.post("/api/agent_apps/{app_id}/versions/{version_id}/run/stream")
async def run_stream(app_id: int, version_id: int, request: Request):
    data = await request.json()
    return StreamingResponse(workflow_engine.run_agent_workflow_stream(
        MemoryDB(), app_id, version_id, data.get("inputs", {}), emit_trace=True), media_type="text/event-stream")


@app.get("/api/agent_apps/{app_id}/runs/{run_id}")
async def run_trace(app_id: int, run_id: str):
    return ok(TRACES.get(run_id))


@app.get("/api/agent_apps/traces/{trace_id}")
async def trace(trace_id: str):
    return ok(TRACES.get(trace_id))


@app.get("/api/agent_apps/{app_id}")
async def detail(app_id: int):
    return ok(app_data())


@app.post("/api/_fixture/reset")
async def reset():
    global GRAPH, REVISION, UNDO_STACK
    GRAPH, REVISION, UNDO_STACK = deepcopy(INITIAL_GRAPH), 0, None
    TRACES.clear()
    return ok({"reset": True})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=18001)
