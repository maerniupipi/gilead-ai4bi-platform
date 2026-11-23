"""AI PPT model configuration available after normal platform login."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...schemas.chatbi_ppt_model import PPTModelOption, PPTModelSelection, PPTModelView
from ...services.chatbi.ppt_settings import ppt_model_options, ppt_model_view, save_ppt_model
from .admin import KeyManagementRoute, key_admin


class PPTModelRoute(KeyManagementRoute):
    validation_message = "AI PPT 模型配置字段不符合约定"


router = APIRouter(prefix="/api/chatbi/ppt-model", tags=["AI PPT 模型配置"],
                   dependencies=[Depends(key_admin)], route_class=PPTModelRoute)


@router.get("", response_model=PPTModelView)
def current(db: Session = Depends(get_db)):
    return ppt_model_view(db)


@router.get("/options", response_model=list[PPTModelOption])
def options(db: Session = Depends(get_db)):
    return ppt_model_options(db)


@router.put("", response_model=PPTModelView)
def save(body: PPTModelSelection, db: Session = Depends(get_db), user_id: int = Depends(key_admin)):
    return save_ppt_model(db, body, user_id)
