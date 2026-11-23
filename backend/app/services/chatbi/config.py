import hashlib
import json
import os
import re
from dataclasses import dataclass



class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message

    def body(self):
        return {"status": self.status, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class Identity:
    user_id: str
    credential_id: str | None = None

    @property
    def owner(self):
        value = json.dumps([self.credential_id, self.user_id], ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(value.encode()).hexdigest()

    @property
    def user(self):
        return self.user_id


def identity(user: str, credential_id: str | None = None) -> Identity:
    if (not isinstance(user, str) or not user.strip() or len(user) > 320
            or any(ord(char) < 32 or ord(char) == 127 for char in user)):
        raise APIError(400, "invalid_user", "user 必须为非空用户标识，最多 320 个字符")
    return Identity(user.strip(), credential_id)


def deployment_environment():
    app_env = os.getenv("APP_ENV", "dev").strip().lower()
    environment = os.getenv("CHATBI_ENV", app_env if app_env in {"uat", "prod"} else "uat").strip().lower()
    if environment not in {"uat", "prod"} or (app_env in {"uat", "prod"} and environment != app_env):
        raise APIError(503, "not_configured", "平台服务环境配置不一致")
    return environment


def runtime_key():
    project = os.getenv("CHATBI_AUTOBI_PROJECT_ID", "").strip()
    app = os.getenv("CHATBI_AGENT_APP_ID", "").strip()
    version = os.getenv("CHATBI_AGENT_VERSION_ID", "").strip()
    if project and project.isdigit():
        return f"autobi:{project}"
    if app and app.isdigit() and (not version or version.isdigit()):
        return f"agent:{app}:{version}"
    raise APIError(503, "not_configured", "请配置 ChatBI 分析项目或智能体")


def model_bindings():
    """Deployment-only AutoBI model overrides; cannot change prompts or permissions."""
    try:
        bindings = json.loads(os.getenv("CHATBI_MODEL_BINDINGS", "{}"))
        allowed = {"knowledge_rewrite", "nl2sql", "ner_retrieval", "bi_summary", "chart_drawing"}
        if not isinstance(bindings, dict) or set(bindings) - allowed:
            raise ValueError()
        for value in bindings.values():
            if (not isinstance(value, dict) or set(value) != {"provider_id", "model_name"}
                    or type(value["provider_id"]) is not int or value["provider_id"] <= 0
                    or not isinstance(value["model_name"], str) or not value["model_name"].strip()):
                raise ValueError()
        return bindings
    except (ValueError, TypeError):
        raise APIError(503, "not_configured", "ChatBI 模型绑定配置错误")


def positive_env(name, default):
    return max(1, int(os.getenv(name, str(default))))


def validate_inputs(inputs):
    """Accept business variables by default; a nonempty allowlist opts into restrictions."""
    try:
        allowed = json.loads(os.getenv("CHATBI_ALLOWED_INPUTS", "[]"))
        if not isinstance(allowed, list) or any(not isinstance(key, str) for key in allowed):
            raise ValueError()
    except (ValueError, TypeError):
        raise APIError(503, "not_configured", "业务变量白名单配置错误")
    reserved = {"user", "user_id", "features", "conversation_id", "history", "history_messages",
                "conversation_history", "history_question", "question", "input", "user_message", "message",
                "workflow_id", "workflow", "app_id", "agent_app_id", "version_id", "workflow_version", "runtime"}
    if set(inputs) & reserved:
        raise APIError(400, "invalid_inputs", "inputs 不能覆盖身份、会话历史或运行配置等保留字段")
    if allowed and set(inputs) - set(allowed):
        raise APIError(400, "invalid_inputs", "inputs 含部署白名单未开放的业务变量")
