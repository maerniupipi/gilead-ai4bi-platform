"""Resolve every service request to a server-owned Key/workflow binding."""
from dataclasses import dataclass
import hashlib
import os
import re
import secrets
import time
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from ...models.chatbi import ChatBIAPIKey
from ...models.agent_app import AgentApp, AgentAppVersion
from .config import APIError, deployment_environment, identity, runtime_key


def key_digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def valid_key(value, environment):
    return bool(re.fullmatch(rf"app-{environment}-[A-Za-z0-9_-]{{43,}}", value))


def key_row(name, environment, raw_key, runtime):
    return ChatBIAPIKey(id=str(uuid4()), name=name, environment=environment,
        key_hash=key_digest(raw_key), key_hint=raw_key[:12] + "…" + raw_key[-4:],
        runtime=runtime, enabled=True)


def bootstrap_environment_key(db):
    """One-time import; a disabled/edited registry row always wins over .env."""
    environment = deployment_environment()
    raw_key = os.getenv("CHATBI_API_KEY", "").strip()
    if not valid_key(raw_key, environment):
        return None
    row = db.query(ChatBIAPIKey).filter_by(key_hash=key_digest(raw_key)).first()
    if row:
        return row
    try:
        runtime = runtime_key()
    except APIError:
        runtime = None
    if runtime and runtime.startswith("agent:"):
        # Convert a legacy floating output version into an explicit version once.
        parts = runtime.split(":")
        query = db.query(AgentAppVersion).filter_by(agent_app_id=int(parts[1]))
        version = query.filter_by(id=int(parts[2])).first() if parts[2] else query.filter_by(is_output=True).first()
        runtime = f"agent:{parts[1]}:{version.id}:{version.workflow_rev or 0}" if version else None
    row = key_row(f"{environment.upper()} 初始服务 Key", environment, raw_key, runtime)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.query(ChatBIAPIKey).filter_by(key_hash=key_digest(raw_key)).one()
    return row


@dataclass(frozen=True)
class ServiceCredential:
    id: str
    runtime: str | None

    def user(self, raw_user):
        return identity(raw_user, self.id)

    def chat_runtime(self, db):
        if not self.runtime:
            raise APIError(503, "not_configured", "请在平台后台为此 Key 绑定工作流和版本")
        if self.runtime.startswith("agent:"):
            parts = self.runtime.split(":")
            app = db.query(AgentApp).filter_by(id=int(parts[1]), is_deleted=False).first()
            version = db.query(AgentAppVersion).filter_by(id=int(parts[2]), agent_app_id=int(parts[1])).first()
            if (not app or not version or version.status not in {"published", "online"}
                    or len(parts) != 4 or int(parts[3]) != (version.workflow_rev or 0)):
                raise APIError(503, "workflow_unavailable", "绑定的工作流版本不可用或已修改，请管理员重新绑定")
        return self.runtime


def resolve_credential(db, authorization):
    environment = deployment_environment()
    bootstrap_environment_key(db)
    if not db.query(ChatBIAPIKey.id).filter_by(environment=environment).first():
        raise APIError(503, "not_configured", "平台服务鉴权尚未配置")
    parts = (authorization or "").split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise APIError(401, "unauthorized", "Authorization header must be provided and start with 'Bearer'")
    if not valid_key(parts[1], environment):
        raise APIError(401, "unauthorized", "Access token is invalid")
    row = db.query(ChatBIAPIKey).filter_by(key_hash=key_digest(parts[1]), environment=environment).first()
    if not row:
        raise APIError(401, "unauthorized", "Access token is invalid")
    if not row.enabled or os.getenv("CHATBI_API_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        raise APIError(403, "forbidden", "The app's API service has been disabled.")
    return ServiceCredential(row.id, row.runtime)


def selected_runtime(db, workflow_id, version_id):
    app = db.query(AgentApp).filter_by(id=workflow_id, is_deleted=False).first()
    version = db.query(AgentAppVersion).filter_by(id=version_id, agent_app_id=workflow_id).first()
    if not app or not version:
        raise HTTPException(400, "请选择工作流所属的有效版本")
    if version.status not in {"published", "online"}:
        raise HTTPException(400, "只能绑定已发布或已上线的版本")
    if not isinstance(version.workflow_json, dict) or not version.workflow_json.get("nodes"):
        raise HTTPException(400, "此版本尚无可执行工作流")
    return f"agent:{app.id}:{version.id}:{version.workflow_rev or 0}"


def key_view(db, row):
    binding = {"workflow_id": None, "workflow_name": None, "version_id": None,
               "version_name": None, "workflow_rev": None, "legacy_config": None}
    if row.runtime and row.runtime.startswith("agent:"):
        parts = row.runtime.split(":")
        app = db.get(AgentApp, int(parts[1]))
        version = db.get(AgentAppVersion, int(parts[2]))
        binding.update(workflow_id=int(parts[1]), workflow_name=app.name if app else "工作流已删除",
            version_id=int(parts[2]), version_name=version.name if version else "版本已删除",
            workflow_rev=int(parts[3]) if len(parts) == 4 else None)
    elif row.runtime:
        binding["legacy_config"] = row.runtime
    return {"id": row.id, "name": row.name, "environment": row.environment, "key_hint": row.key_hint,
            "enabled": row.enabled, "created_at": row.created_at, "updated_at": row.updated_at, **binding}


def create_key(db, body):
    runtime = selected_runtime(db, body.workflow_id, body.version_id)
    raw_key = body.api_key.get_secret_value().strip() if body.api_key is not None else "app-" + body.environment + "-" + secrets.token_urlsafe(32)
    if not valid_key(raw_key, body.environment):
        raise HTTPException(400, "Key 格式必须与环境一致，且随机部分至少 43 位")
    if db.query(ChatBIAPIKey.id).filter_by(key_hash=key_digest(raw_key)).first():
        raise HTTPException(409, "该 Key 已存在，请编辑已有绑定")
    row = key_row(body.name, body.environment, raw_key, runtime)
    row.enabled = body.enabled
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "该 Key 已存在，请编辑已有绑定")
    # Imported secrets are not reflected in the response.
    return {"key": key_view(db, row), "api_key": raw_key if body.api_key is None else None}


def update_key(db, row, body):
    row.runtime = selected_runtime(db, body.workflow_id, body.version_id)
    row.name, row.enabled, row.updated_at = body.name, body.enabled, int(time.time())
    db.commit()
    return key_view(db, row)
