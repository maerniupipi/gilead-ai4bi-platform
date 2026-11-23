"""Platform configuration available to every logged-in platform user."""
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.permissions import require_platform_user
from ...models.agent_app import AgentApp, AgentAppVersion
from ...models.chatbi import ChatBIAPIKey
from ...schemas.chatbi_keys import KeyBinding, KeyCreate, KeyCreated, KeyEnabled, KeyView
from ...services.chatbi.credentials import bootstrap_environment_key, create_key, key_view, update_key
from ...services.chatbi.config import APIError


def key_admin(request: Request, db: Session = Depends(get_db)):
    return require_platform_user(request, db)


class KeyManagementRoute(APIRoute):
    validation_message = "Key 配置请求字段不符合约定"
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def wrapped(request):
            try:
                response = await handler(request)
                response.headers["Cache-Control"] = "no-store"
                return response
            except RequestValidationError:
                # Default validation logging may include a raw imported Key.
                raise HTTPException(400, self.validation_message)
            except APIError as exc:
                raise HTTPException(exc.status, exc.message)
        return wrapped


router = APIRouter(prefix="/api/chatbi/keys", tags=["ChatBI 服务 Key 管理"], dependencies=[Depends(key_admin)], route_class=KeyManagementRoute)




def get_key(db, key_id):
    row = db.get(ChatBIAPIKey, str(key_id))
    if not row:
        raise HTTPException(404, "Key 配置不存在")
    return row


@router.get("", response_model=list[KeyView])
def list_keys(db: Session = Depends(get_db)):
    bootstrap_environment_key(db)
    return [key_view(db, row) for row in db.query(ChatBIAPIKey).order_by(ChatBIAPIKey.created_at, ChatBIAPIKey.id).all()]


@router.get("/workflow-options")
def workflow_options(db: Session = Depends(get_db)):
    apps = db.query(AgentApp).filter_by(is_deleted=False).order_by(AgentApp.name).all()
    versions = db.query(AgentAppVersion).filter(AgentAppVersion.status.in_(["published", "online"])).all()
    return [{"id": app.id, "name": app.name, "versions": [
        {"id": v.id, "name": v.name, "status": v.status, "workflow_rev": v.workflow_rev or 0}
        for v in versions if v.agent_app_id == app.id and isinstance(v.workflow_json, dict) and v.workflow_json.get("nodes")
    ]} for app in apps if any(v.agent_app_id == app.id and isinstance(v.workflow_json, dict) and v.workflow_json.get("nodes") for v in versions)]


@router.post("", status_code=201, response_model=KeyCreated)
def add_key(body: KeyCreate, db: Session = Depends(get_db)):
    bootstrap_environment_key(db)
    return create_key(db, body)


@router.put("/{key_id}", response_model=KeyView)
def edit_key(key_id: UUID, body: KeyBinding, db: Session = Depends(get_db)):
    return update_key(db, get_key(db, key_id), body)


@router.patch("/{key_id}/enabled", response_model=KeyView)
def enable_key(key_id: UUID, body: KeyEnabled, db: Session = Depends(get_db)):
    row = get_key(db, key_id)
    row.enabled, row.updated_at = body.enabled, int(time.time())
    db.commit()
    return key_view(db, row)
