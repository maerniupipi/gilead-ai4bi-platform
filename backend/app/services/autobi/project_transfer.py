"""Portable lab settings, with fresh local resource selections on every import."""
from copy import deepcopy
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...repositories.autobi import repository as repo
from ...schemas.autobi import AutobiProjectImport
from .api_access_id import allocate_unique_api_access_id
from .service import _dump_config, ensure_default_autobi_folder, get_autobi_project_service


EXPORT_FORMAT = "chat-bi-lab-export"
EXPORT_VERSION = 1
MODEL_BINDINGS = ("knowledge_rewrite", "nl2sql", "ner_retrieval", "bi_summary", "chart_drawing")


def portable_config(config):
    """Keep every non-binding setting and explicitly override merged model defaults."""
    if not isinstance(config, dict) or not isinstance(config.get("request"), dict):
        raise HTTPException(400, "无效的实验室配置：缺少 request 对象")
    request = config["request"]
    if "advanced_config" in request and not isinstance(request["advanced_config"], dict):
        raise HTTPException(400, "无效的实验室配置：advanced_config 必须是对象")
    if "messages" in request and (not isinstance(request["messages"], list)
            or any(not isinstance(message, dict) for message in request["messages"])):
        raise HTTPException(400, "无效的实验室配置：messages 必须是对象数组")
    if "stream" in request and not isinstance(request["stream"], bool):
        raise HTTPException(400, "无效的实验室配置：stream 必须是布尔值")
    bindings = config.get("model_bindings", {})
    if not isinstance(bindings, dict) or any(not isinstance(binding, dict) for binding in bindings.values()):
        raise HTTPException(400, "无效的实验室配置：model_bindings 必须是模型绑定对象")
    result = deepcopy(config)
    result["knowledge_base_id"] = None
    result["model_bindings"] = {
        key: {**deepcopy(bindings.get(key, {})), "provider_id": None, "model_name": ""}
        for key in dict.fromkeys((*MODEL_BINDINGS, *bindings))
    }
    return result


def export_autobi_project_service(db: Session, project_id: int, space_id: int = None):
    project = get_autobi_project_service(db, project_id, space_id)
    return {
        "format": EXPORT_FORMAT,
        "formatVersion": EXPORT_VERSION,
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "project": {"name": project["name"], "description": project["description"]},
        "config_json": portable_config(project["config_json"]),
    }


def import_autobi_project_service(db: Session, body: AutobiProjectImport, space_id: int = None):
    payload = body.payload
    if payload.get("format") != EXPORT_FORMAT:
        raise HTTPException(400, "请使用本系统导出的实验室 JSON 配置文件")
    if type(payload.get("formatVersion")) is not int or payload["formatVersion"] != EXPORT_VERSION:
        raise HTTPException(400, "不支持的实验室导出文件版本")
    project = payload.get("project")
    if not isinstance(project, dict):
        raise HTTPException(400, "无效的实验室导出文件：缺少 project 对象")
    name = body.name if body.name is not None else project.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 255:
        raise HTTPException(400, "实验室名称须为 1 至 255 个字符")
    description = project.get("description")
    if description is not None and not isinstance(description, str):
        raise HTTPException(400, "实验室描述必须是文本")
    config = portable_config(payload.get("config_json"))
    try:
        folder_id = body.folder_id if body.folder_id is not None else ensure_default_autobi_folder(db, space_id)
        if repo.get_autobi_folder(db, folder_id, space_id) is None:
            raise HTTPException(404, "文件夹不存在")
        row = repo.create_autobi_project(db, name.strip(), description, _dump_config(config), None,
                                        allocate_unique_api_access_id(db), folder_id, space_id)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return get_autobi_project_service(db, row.id, space_id)
