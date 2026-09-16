from typing import Annotated

from fastapi import APIRouter, Depends

from aidevops.dependencies import SessionDependency, require_permissions
from rbac.models import User
from rbac.schemas.authorization import PermissionResponse
from rbac.selectors.authorization import list_permissions


router = APIRouter(prefix="/api/permissions", tags=["权限字典"])


@router.get("/", response_model=list[PermissionResponse], description="只读查询权限字典，不创建或修改内置权限。")
async def permissions_list(session: SessionDependency, actor: Annotated[User, Depends(require_permissions("rbac.permission.view"))], search: str = "") -> list[PermissionResponse]:
    return [PermissionResponse.model_validate(item) for item in await list_permissions(session, search.strip())]
