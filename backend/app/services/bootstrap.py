"""新环境数据库初始化种子数据。"""
from __future__ import annotations

import hashlib
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import AgentAppFolder, AutobiFolder, Space, User, UserSpaceLastAccess, UserSpaceRole
from ..models.eval import EvalComparisonTemplate, EvalConfig, EvalFolder
from ..models.xlsx_qa import XlsxQaPptTemplate
from .eval.eval_comparison_template_defaults import get_system_template_payloads


DEFAULT_SPACE_ID = 1
DEFAULT_ADMIN_ID = 1


def hash_password(password: str) -> str:
    """与当前登录逻辑保持一致。"""
    return hashlib.sha256(password.encode()).hexdigest()


def _ensure_default_space(
    db: Session,
    *,
    name: str = "默认空间",
    code: str = "default",
    description: str = "系统默认空间",
) -> Space:
    space = db.query(Space).filter(Space.id == DEFAULT_SPACE_ID).first()
    if space is None:
        space = Space(id=DEFAULT_SPACE_ID, name=name, code=code, description=description, is_active=True)
        db.add(space)
        db.flush()
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SELECT setval(pg_get_serial_sequence('spaces', 'id'), max(id)) FROM spaces"))
        return space

    space.name = space.name or name
    space.code = space.code or code
    space.description = space.description or description
    space.is_active = True
    db.flush()
    return space


def _ensure_super_admin(
    db: Session,
    *,
    username: str,
    password: str,
    display_name: str,
    space_id: int = DEFAULT_SPACE_ID,
    update_existing_password: bool = False,
) -> User:
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        user = User(
            id=DEFAULT_ADMIN_ID,
            username=username,
            display_name=display_name or username,
            password_hash=hash_password(password),
            system_role="super_admin",
            is_active=True,
            is_preset_admin=True,
        )
        db.add(user)
        db.flush()
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SELECT setval(pg_get_serial_sequence('users', 'id'), max(id)) FROM users"))
    else:
        user.display_name = user.display_name or display_name or username
        user.system_role = "super_admin"
        user.is_active = True
        user.is_preset_admin = True
        if update_existing_password or not user.password_hash:
            user.password_hash = hash_password(password)
        db.flush()

    role = (
        db.query(UserSpaceRole)
        .filter(UserSpaceRole.user_id == user.id, UserSpaceRole.space_id == space_id)
        .first()
    )
    if role is None:
        db.add(UserSpaceRole(user_id=user.id, space_id=space_id, role="owner"))
    else:
        role.role = "owner"

    last = db.query(UserSpaceLastAccess).filter(UserSpaceLastAccess.user_id == user.id).first()
    if last is None:
        db.add(UserSpaceLastAccess(user_id=user.id, last_space_id=space_id))
    else:
        last.last_space_id = space_id

    db.flush()
    return user


def _ensure_system_folder(db: Session, model, *, space_id: int, name: str = "默认文件夹") -> None:
    folder = (
        db.query(model)
        .filter(model.space_id == space_id, model.is_system.is_(True))
        .order_by(model.id.asc())
        .first()
    )
    if folder is not None:
        return

    legacy = (
        db.query(model)
        .filter(model.space_id == space_id, model.name == name)
        .order_by(model.id.asc())
        .first()
    )
    if legacy is not None:
        legacy.is_system = True
        legacy.sort_order = legacy.sort_order or 0
        db.flush()
        return

    db.add(model(space_id=space_id, name=name, sort_order=0, is_system=True))
    db.flush()


def _ensure_eval_folder(db: Session, *, space_id: int) -> None:
    exists = (
        db.query(EvalFolder)
        .filter(EvalFolder.space_id == space_id, EvalFolder.is_system.is_(True))
        .first()
    )
    if exists is not None:
        return
    db.add(
        EvalFolder(
            space_id=space_id,
            parent_id=None,
            name="默认文件夹",
            description="系统默认评测文件夹",
            sort_order=0,
            is_system=True,
        )
    )
    db.flush()


def _ensure_eval_configs(db: Session) -> None:
    defaults = [
        ("eval_concurrency", "3", "评测任务并发数"),
        ("eval_target_timeout", "180", "单个目标调用超时(秒)"),
        ("eval_target_retry", "1", "目标调用重试次数"),
        ("eval_judge_retry", "2", "LLM评判重试次数"),
    ]
    for key, value, description in defaults:
        exists = db.query(EvalConfig).filter(EvalConfig.key == key).first()
        if exists is None:
            db.add(EvalConfig(key=key, value=value, description=description))
    db.flush()


def _ensure_eval_comparison_templates(db: Session, *, space_id: int) -> None:
    exists = db.query(EvalComparisonTemplate.id).filter(EvalComparisonTemplate.space_id == space_id).first()
    if exists is not None:
        return
    for payload in get_system_template_payloads():
        db.add(EvalComparisonTemplate(space_id=space_id, **payload))
    db.flush()


def get_builtin_ppt_templates() -> Iterable[dict]:
    return [
        dict(id="executive", name="商务简报", description="专业商务风格，侧边栏布局", layout="sidebar", sort_order=10,
             colors={"accent": "#16A34A", "accent_dark": "#085F37", "accent_soft": "#E8F8EE", "bg": "#F7FAFC", "panel": "#FFFFFF", "text": "#17241F", "muted": "#64748B", "table_header": "#0F7A4B", "table_alt": "#F1FAF5", "palette": ["#16A34A", "#2563EB", "#F59E0B", "#DC2626", "#7C3AED", "#0E7480"]}),
        dict(id="insight", name="洞察分析", description="蓝色洞察风格，顶部横幅布局", layout="header", sort_order=20,
             colors={"accent": "#2563EB", "accent_dark": "#1E3A8A", "accent_soft": "#E8F0FF", "bg": "#F8FAFC", "panel": "#FFFFFF", "text": "#0F172A", "muted": "#64748B", "table_header": "#1D4E89", "table_alt": "#F1F5FF", "palette": ["#2563EB", "#10B981", "#F97316", "#8B5CF6", "#06B6D4", "#E11D48"]}),
        dict(id="clean", name="简约数据", description="极简干净风格，最小化布局", layout="minimal", sort_order=30,
             colors={"accent": "#334155", "accent_dark": "#0F172A", "accent_soft": "#F1F5F9", "bg": "#FFFFFF", "panel": "#FFFFFF", "text": "#111827", "muted": "#6B7280", "table_header": "#334155", "table_alt": "#F8FAFC", "palette": ["#334155", "#0E7480", "#65A30D", "#CA8A04", "#7C2D12", "#7E22CE"]}),
        dict(id="midnight", name="午夜深蓝", description="深蓝夜间风格，全屏暗色布局", layout="dark_full", sort_order=40,
             colors={"accent": "#FFB224", "accent_dark": "#0D1B2A", "accent_soft": "#1B2D44", "bg": "#0D1B2A", "panel": "#15263B", "text": "#E8ECF1", "muted": "#8B9DB3", "table_header": "#1B3A5C", "table_alt": "#122236", "palette": ["#FFB224", "#38BDF8", "#A78BFA", "#34D399", "#FB7185", "#60A5FA"]}),
        dict(id="coral", name="珊瑚活力", description="珊瑚活力风格，对角线布局", layout="diagonal", sort_order=50,
             colors={"accent": "#F96167", "accent_dark": "#C0392B", "accent_soft": "#FFF1F0", "bg": "#FFFAF7", "panel": "#FFFFFF", "text": "#2D1B1B", "muted": "#9C7A7A", "table_header": "#E84D4D", "table_alt": "#FFF5F4", "palette": ["#F96167", "#F97316", "#FBBF24", "#2DC653", "#38BDF8", "#A78BFA"]}),
        dict(id="teal", name="青绿信赖", description="青绿信赖风格，角落布局", layout="corner", sort_order=60,
             colors={"accent": "#0D9488", "accent_dark": "#115E59", "accent_soft": "#ECFDF5", "bg": "#F0FDFA", "panel": "#FFFFFF", "text": "#132B2B", "muted": "#6B8A87", "table_header": "#0F766E", "table_alt": "#F0FDFA", "palette": ["#0D9488", "#06B6D4", "#8B5CF6", "#F59E0B", "#EF4444", "#22C55E"]}),
        dict(id="berry", name="浆果奶油", description="浆果甜美风格，右侧面板布局", layout="right_panel", sort_order=70,
             colors={"accent": "#9D174D", "accent_dark": "#701238", "accent_soft": "#FDF2F8", "bg": "#FFFAFC", "panel": "#FFFFFF", "text": "#2A1522", "muted": "#9C7A8C", "table_header": "#831843", "table_alt": "#FDF2F8", "palette": ["#9D174D", "#A26769", "#BE185D", "#D97706", "#6D28D9", "#0891B2"]}),
        dict(id="charcoal", name="炭黑深沉", description="炭黑深沉风格，暗色头部布局", layout="dark_header", sort_order=80,
             colors={"accent": "#F59E0B", "accent_dark": "#1E1E1E", "accent_soft": "#2A2A2A", "bg": "#1E1E1E", "panel": "#2A2A2A", "text": "#E5E5E5", "muted": "#8A8A8A", "table_header": "#3A3A3A", "table_alt": "#242424", "palette": ["#F59E0B", "#38BDF8", "#A3E635", "#F472B6", "#C084FC", "#FB923C"]}),
    ]


def _ensure_ppt_templates(db: Session) -> None:
    for payload in get_builtin_ppt_templates():
        exists = db.query(XlsxQaPptTemplate).filter(XlsxQaPptTemplate.id == payload["id"]).first()
        if exists is None:
            db.add(XlsxQaPptTemplate(**payload, is_builtin=True))
    db.flush()


def seed_initial_data(
    db: Session,
    *,
    admin_username: str = "admin",
    admin_password: str = "Admin@123456",
    admin_display_name: str = "超级管理员",
    space_name: str = "默认空间",
    space_code: str = "default",
    space_description: str = "系统默认空间",
    update_existing_admin_password: bool = False,
) -> dict[str, int | str]:
    """写入新部署必须存在的默认数据，重复执行保持幂等。"""
    space = _ensure_default_space(db, name=space_name, code=space_code, description=space_description)
    admin = _ensure_super_admin(
        db,
        username=admin_username,
        password=admin_password,
        display_name=admin_display_name,
        space_id=space.id,
        update_existing_password=update_existing_admin_password,
    )
    _ensure_system_folder(db, AutobiFolder, space_id=space.id)
    _ensure_system_folder(db, AgentAppFolder, space_id=space.id)
    _ensure_eval_folder(db, space_id=space.id)
    _ensure_eval_configs(db)
    _ensure_eval_comparison_templates(db, space_id=space.id)
    _ensure_ppt_templates(db)
    db.commit()
    return {
        "space_id": int(space.id),
        "space_code": space.code,
        "admin_id": int(admin.id),
        "admin_username": admin.username,
    }
