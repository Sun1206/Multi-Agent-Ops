from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import SessionDependency, require_permissions
from app.models import User
from app.schemas.rbac import PermissionResponse
from app.selectors.rbac import list_permissions


router = APIRouter(prefix="/api/permissions", tags=["权限字典"])


@router.get("/", response_model=list[PermissionResponse])
async def permissions_list(session: SessionDependency, actor: Annotated[User, Depends(require_permissions("rbac.permission.view"))], search: str = "") -> list[PermissionResponse]:
    """GET /api/permissions/：只读查询权限字典，不创建或修改内置权限。"""
    return [PermissionResponse.model_validate(item) for item in await list_permissions(session, search.strip())]
