# 装配智能体配置管理接口，仅保存声明，不调用外部运行服务。

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.agent_registry import CATALOG, action_catalog
from app.api.dependencies import SessionDependency, require_permissions
from app.models import User
from app.schemas.agent_config import CloneRequest, McpCreate, McpPatch, ProviderCreate, ProviderPatch, SkillCreate, SkillPatch, StrategyPatch
from app.selectors.agent_config import get_resource, list_resources, marketplace_response, resource_response, strategy_response
from app.selectors.permissions import user_has_permissions
from app.services.agent_config import audit_config, clone_skill, mutate_resource, mutate_strategy, remove_resource


router = APIRouter(prefix='/api/aiops/admin', tags=['智能体配置'])
ConfigViewer = Annotated[User, Depends(require_permissions('aiops.config.view'))]
ConfigManager = Annotated[User, Depends(require_permissions('aiops.config.manage'))]


@router.get('/config/', description="读取默认策略，未初始化时返回无副作用默认值。")
async def get_config(session: SessionDependency, actor: ConfigViewer):
    return await strategy_response(session)


@router.put('/config/', description="保存显式提交的策略字段，并与配置审计一起提交。")
async def put_config(body: StrategyPatch, request: Request, session: SessionDependency, actor: ConfigManager):
    values = body.model_dump(exclude_unset=True)
    item = await mutate_strategy(session, dict(values))
    await audit_config(session, request, actor, 'update_agent_config', 'aiops_config', item.id, list(values))
    await session.commit()
    return await strategy_response(session)


@router.get('/actions/', description="输出 Action 声明及风险统计，明确尚未具备运行处理器。")
async def get_actions(actor: ConfigViewer):
    return action_catalog()


@router.get('/providers/presets/', description="输出静态供应商填表预设，不保证模型当前支持情况或发起探测。")
async def get_presets(actor: ConfigViewer):
    return {'presets': CATALOG['MODEL_PROVIDER_PRESETS']}


@router.get('/skills/marketplace/', description="输出本地 Skill 能力包目录及当前用户的编辑/克隆提示。")
async def get_marketplace(session: SessionDependency, actor: ConfigViewer):
    can_manage = await user_has_permissions(session, actor, ('aiops.config.manage',))
    return await marketplace_response(session, can_manage=can_manage)


@router.post('/skills/{identifier}/clone/', status_code=201, description="克隆 Skill 为团队自定义版本，保持源记录与内置属性不变。")
async def post_clone(identifier: int, body: CloneRequest, request: Request, session: SessionDependency, actor: ConfigManager):
    item = await clone_skill(session, identifier, body.model_dump(exclude_unset=True))
    await audit_config(session, request, actor, 'clone_skill', 'aiops_skill', item.id, ['source_skill_id'])
    await session.commit()
    return resource_response('skills', item)


def register_resource_routes(kind: str, create_model, patch_model) -> None:
    prefix = '/' + kind

    async def list_items(session: SessionDependency, actor: ConfigViewer):
        return [resource_response(kind, item) for item in await list_resources(session, kind)]

    async def get_item(identifier: int, session: SessionDependency, actor: ConfigViewer):
        return resource_response(kind, await get_resource(session, kind, identifier))

    async def create_item(body: create_model, request: Request, session: SessionDependency, actor: ConfigManager):
        values = body.model_dump()
        item = await mutate_resource(session, kind, dict(values))
        await audit_config(session, request, actor, 'create_aiops_config', kind, item.id, list(body.model_fields_set))
        await session.commit()
        return resource_response(kind, item)

    async def patch_item(identifier: int, body: patch_model, request: Request, session: SessionDependency, actor: ConfigManager):
        values = body.model_dump(exclude_unset=True)
        item = await mutate_resource(session, kind, dict(values), identifier)
        await audit_config(session, request, actor, 'update_aiops_config', kind, item.id, list(values))
        await session.commit()
        return resource_response(kind, item)

    async def delete_item(identifier: int, request: Request, session: SessionDependency, actor: ConfigManager):
        await remove_resource(session, kind, identifier)
        await audit_config(session, request, actor, 'delete_aiops_config', kind, identifier, [])
        await session.commit()
        return Response(status_code=204)

    for function, path, method, code in [(list_items, prefix + '/', 'GET', 200), (create_item, prefix + '/', 'POST', 201), (get_item, prefix + '/{identifier}/', 'GET', 200), (patch_item, prefix + '/{identifier}/', 'PATCH', 200), (delete_item, prefix + '/{identifier}/', 'DELETE', 204)]:
        function.__name__ = kind.replace('-', '_') + '_' + function.__name__
        router.add_api_route(path, function, methods=[method], status_code=code, description={"list_items": "读取公开配置列表，凭据仅以脱敏状态返回。", "get_item": "读取指定配置的详情，使用路径 ID 定位服务端对象。", "create_item": "校验并创建自定义配置，加密秘密和安全日志在同事务提交。", "patch_item": "仅更新显式可写字段，未提交字段及凭据保持原值。", "delete_item": "删除非内置配置并清理策略引用，保护其他业务记录。"}.get(function.__name__.removeprefix(kind.replace('-', '_') + '_')))


register_resource_routes('providers', ProviderCreate, ProviderPatch)
register_resource_routes('mcp-servers', McpCreate, McpPatch)
register_resource_routes('skills', SkillCreate, SkillPatch)
