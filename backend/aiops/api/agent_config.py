# 装配配置管理和用户显式触发的模型诊断接口，不启动MCP或执行工具。

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from aiops.agent_registry import action_catalog, provider_presets
from aidevops.dependencies import SessionDependency, require_permissions
from rbac.models import User
from aiops.schemas.agent_config import CloneRequest, McpCreate, McpPatch, ProviderCreate, ProviderPatch, SkillCreate, SkillPatch, StrategyPatch
from aiops.selectors.agent_config import get_resource, list_resources, marketplace_response, resource_response, strategy_response
from rbac.selectors.permissions import user_has_permissions
from aiops.services.agent_config import audit_config, clone_skill, mutate_resource, mutate_strategy, remove_resource
from aiops.schemas.provider_runtime import ConnectionResult, ModelCatalogResult
from aiops.services.provider_runtime import diagnose_provider
from aiops.services.mcp_runtime import diagnose_mcp


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
    return {'presets': provider_presets()}


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


# 使用管理权限触发固定短文本探测；成功200、远端诊断失败400，秘密不回显。
@router.post('/providers/{identifier}/test_connection/', response_model=ConnectionResult, description='测试已保存提供商的文本连接，并原子保存安全诊断状态和审计。')
async def test_provider_connection(identifier: int, request: Request, session: SessionDependency, actor: ConfigManager):
    result, status = await diagnose_provider(identifier, request, session, actor, connection=True)
    return JSONResponse(status_code=status, content=result)


# probe默认true兼容旧页面；false只读供应商目录。GET仍需管理权限并记录审计。
@router.get('/providers/{identifier}/models/', response_model=ModelCatalogResult, description='获取模型目录并可选验证文本及工具声明能力，不执行工具或保存推荐模型。')
async def get_provider_models(identifier: int, request: Request, session: SessionDependency, actor: ConfigManager, probe: bool = True):
    result, status = await diagnose_provider(identifier, request, session, actor, probe=probe)
    if status != 200:
        return JSONResponse(status_code=status, content=result)
    return result


# 管理权限触发HTTP握手；不启动STDIO、不把平台声明误报成可执行连接。
@router.post('/mcp-servers/{identifier}/test_connection/', description='测试HTTP MCP握手并记录安全审计，不执行工具或启动子进程。')
async def test_mcp_connection(identifier: int, request: Request, session: SessionDependency, actor: ConfigManager):
    payload, status = await diagnose_mcp(identifier, request, session, actor)
    return JSONResponse(status_code=status, content=payload)


# 复用HTTP握手查询有界工具目录，返回旧页面tools/count/diagnostics结构。
@router.get('/mcp-servers/{identifier}/list_tools/', description='发现HTTP MCP工具声明并应用白名单与只读过滤，不调用工具或修改配置。')
async def get_mcp_tools(identifier: int, request: Request, session: SessionDependency, actor: ConfigManager):
    payload, status = await diagnose_mcp(identifier, request, session, actor, tools=True)
    return JSONResponse(status_code=status, content=payload)


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
