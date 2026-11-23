"""AI 创建助手：工具执行（查库，不抛 HTTP）。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ...models.agent_app import AgentApp
from ...models.autobi_project import AutobiProject
from ...models.knowledge_base import KnowledgeBase, KbTableStructure
from ...models.model_provider import ModelProvider

logger = logging.getLogger(__name__)


def _node_count(workflow_json: Optional[dict]) -> int:
    if not workflow_json or not isinstance(workflow_json, dict):
        return 0
    nodes = workflow_json.get("nodes") or []
    return len(nodes) if isinstance(nodes, list) else 0


def _summarize_lab_config(config_json: Optional[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not config_json:
        return out
    try:
        cfg = json.loads(config_json) if isinstance(config_json, str) else config_json
    except (json.JSONDecodeError, TypeError):
        return out
    if isinstance(cfg, dict):
        kb_id = cfg.get("knowledge_base_id")
        if kb_id is not None:
            out["knowledge_base_id"] = kb_id
        req = cfg.get("request") or {}
        if isinstance(req, dict) and req.get("messages"):
            out["has_request_messages"] = True
    return out


class AiCreatorToolExecutor:
    def __init__(self, db: Session):
        self.db = db

    def run(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = args or {}
        try:
            if tool_name == "list_agent_apps":
                return self._list_agent_apps(args)
            if tool_name == "list_lab_projects":
                return self._list_lab_projects(args)
            if tool_name == "get_data_tables":
                return self._get_data_tables(args)
            if tool_name == "get_model_providers":
                return self._get_model_providers()
            return {"error": f"未知工具: {tool_name}", "status": "failed"}
        except Exception as e:  # noqa: BLE001
            logger.exception("tool %s failed", tool_name)
            return {"error": str(e), "status": "failed"}

    def _list_agent_apps(self, args: Dict[str, Any]) -> Dict[str, Any]:
        keyword = (args.get("keyword") or "").strip() or None
        limit = int(args.get("limit") or 20)
        limit = max(1, min(limit, 50))
        q = (
            self.db.query(AgentApp)
            .filter(AgentApp.is_deleted == False)  # noqa: E712
            .options(joinedload(AgentApp.versions))
            .order_by(AgentApp.updated_at.desc())
        )
        if keyword:
            kw = f"%{keyword}%"
            q = q.filter(
                or_(
                    AgentApp.name.like(kw),
                    AgentApp.description.like(kw),
                )
            )
        rows: List[AgentApp] = q.offset(0).limit(limit).all()
        apps: List[Dict[str, Any]] = []
        for row in rows:
            versions = sorted(
                row.versions or [],
                key=lambda v: (v.created_at or datetime.min, v.id),
                reverse=True,
            )
            latest = versions[0] if versions else None
            online_like = any(
                (v.status or "") in ("online", "published") for v in versions
            )
            nc = _node_count(latest.workflow_json if latest else None)
            apps.append(
                {
                    "id": row.id,
                    "folder_id": int(getattr(row, "folder_id", 0) or 0),
                    "name": row.name,
                    "description": (row.description or "")[:200],
                    "has_online_version": online_like,
                    "latest_version_id": latest.id if latest else None,
                    "node_count": nc,
                }
            )
        return {"apps": apps, "total": len(apps), "status": "ok"}

    def _list_lab_projects(self, args: Dict[str, Any]) -> Dict[str, Any]:
        keyword = (args.get("keyword") or "").strip().lower()
        limit = int(args.get("limit") or 20)
        limit = max(1, min(limit, 50))
        q = (
            self.db.query(AutobiProject)
            .filter(AutobiProject.is_deleted == False)  # noqa: E712
            .order_by(AutobiProject.id.desc())
        )
        rows = q.limit(200).all()
        projects: List[Dict[str, Any]] = []
        for row in rows:
            name = row.name or ""
            desc = (row.description or "")[:300]
            if keyword and keyword not in name.lower() and keyword not in desc.lower():
                continue
            hint = _summarize_lab_config(row.config_json)
            projects.append(
                {
                    "id": row.id,
                    "api_access_id": row.api_access_id,
                    "name": name,
                    "description": desc,
                    "knowledge_base_id": row.knowledge_base_id,
                    "config_hint": hint,
                    "updated_at": str(row.updated_at) if row.updated_at else None,
                }
            )
            if len(projects) >= limit:
                break
        return {"projects": projects, "total": len(projects), "status": "ok"}

    def _get_data_tables(self, args: Dict[str, Any]) -> Dict[str, Any]:
        keyword = (args.get("keyword") or "").strip().lower()
        limit = int(args.get("limit") or 10)
        limit = max(1, min(limit, 30))
        q = (
            self.db.query(KnowledgeBase)
            .filter(KnowledgeBase.is_deleted == False)  # noqa: E712
            .options(
                joinedload(KnowledgeBase.kb_table_structures).joinedload(
                    KbTableStructure.kb_table_fields
                )
            )
            .limit(80)
        )
        tables_out: List[Dict[str, Any]] = []
        for kb in q.all():
            for ts in kb.kb_table_structures or []:
                tname = ts.table_name or ""
                alias = ts.table_alias or ""
                blob = f"{tname} {alias}".lower()
                cols: List[Dict[str, Any]] = []
                for f in ts.kb_table_fields or []:
                    if not getattr(f, "is_enabled", True):
                        continue
                    cols.append(
                        {
                            "name": f.field_name,
                            "type": f.field_type,
                            "description": (f.field_alias or "")[:120],
                        }
                    )
                    blob += f" {f.field_name}".lower()
                if keyword and keyword not in blob:
                    continue
                tables_out.append(
                    {
                        "knowledge_base_id": kb.id,
                        "knowledge_base_name": kb.name,
                        "table_name": tname,
                        "display_name": alias or tname,
                        "columns": cols[:40],
                        "column_count": len(cols),
                    }
                )
                if len(tables_out) >= limit:
                    return {"tables": tables_out, "total": len(tables_out), "status": "ok"}
        return {"tables": tables_out, "total": len(tables_out), "status": "ok"}

    def _get_model_providers(self) -> Dict[str, Any]:
        rows = self.db.query(ModelProvider).filter(ModelProvider.is_active == True).limit(100).all()  # noqa: E712
        providers: List[Dict[str, Any]] = []
        for p in rows:
            models: List[Dict[str, str]] = []
            raw = p.models or ""
            if raw.strip():
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        for m in parsed:
                            if isinstance(m, str):
                                models.append({"name": m, "display_name": m})
                            elif isinstance(m, dict):
                                name = str(m.get("name") or m.get("id") or "")
                                if name:
                                    models.append(
                                        {
                                            "name": name,
                                            "display_name": str(
                                                m.get("display_name") or m.get("label") or name
                                            ),
                                        }
                                    )
                except (json.JSONDecodeError, TypeError):
                    pass
            providers.append(
                {
                    "provider_id": p.id,
                    "provider_name": p.name,
                    "protocol": p.protocol or "openai",
                    "models": models,
                }
            )
        return {"providers": providers, "status": "ok"}
