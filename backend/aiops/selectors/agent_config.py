# 查询配置对象并以白名单序列化，不泄露存储凭据。

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiops.models import AIOpsAgentConfig, AIOpsMCPServer, AIOpsModelProvider, AIOpsSkill
from aiops.schemas.agent_config import McpPatch, ProviderPatch, SkillPatch, StrategyPatch
from aidevops.config_secrets import transform_auth, usable_secret


RESOURCE_MODELS = {'providers': AIOpsModelProvider, 'mcp-servers': AIOpsMCPServer, 'skills': AIOpsSkill}
RESOURCE_INPUTS = {'providers': ProviderPatch, 'mcp-servers': McpPatch, 'skills': SkillPatch}


async def get_resource(session: AsyncSession, kind: str, identifier: int, *, lock=False):
    model = RESOURCE_MODELS[kind]
    statement = select(model).where(model.id == identifier).execution_options(populate_existing=True)
    if lock:
        statement = statement.with_for_update()
    item = await session.scalar(statement)
    if item is None:
        raise HTTPException(status_code=404, detail='配置对象不存在。')
    return item


async def list_resources(session: AsyncSession, kind: str):
    model = RESOURCE_MODELS[kind]
    statement = select(model)
    if kind != 'providers':
        statement = statement.order_by(model.is_builtin)
    return list((await session.scalars(statement.order_by(model.name, model.id))).all())


def provider_hint(item) -> str:
    if not item.is_enabled:
        return '提供商未启用。'
    if not item.base_url or not item.default_model:
        return '请填写地址和默认模型；实际连接尚未验证。'
    if not usable_secret(item.api_key_encrypted):
        return 'API Key 未配置、无法解密或服务端加密密钥不可用。'
    return ''


def resource_response(kind: str, item) -> dict:
    fields = RESOURCE_INPUTS[kind].model_fields
    response = {name: getattr(item, name) for name in fields if name != 'api_key'}
    response.update(id=item.id, created_at=item.created_at, updated_at=item.updated_at)
    if kind == 'providers':
        hint = provider_hint(item)
        response.update(has_api_key=bool(item.api_key_encrypted), runtime_ready=not hint, setup_hint=hint, last_test_status=item.last_test_status, last_test_message='连接测试记录存在。' if item.last_test_message else '')
    else:
        response['is_builtin'] = item.is_builtin
        if kind == 'mcp-servers':
            response['auth_config'] = transform_auth(item.auth_config, masked=True)
    return response


async def strategy_response(session: AsyncSession) -> dict:
    item = await session.scalar(select(AIOpsAgentConfig).where(AIOpsAgentConfig.name == 'default'))
    values = StrategyPatch().model_dump()
    if item is not None:
        values.update({name: getattr(item, name) for name in values})
    provider_id = values.pop('default_provider_id')
    provider = await session.get(AIOpsModelProvider, provider_id) if provider_id is not None else None
    lite = None
    if provider is not None:
        full = resource_response('providers', provider)
        lite = {name: full[name] for name in ('id', 'name', 'provider_type', 'default_model', 'is_enabled', 'runtime_ready', 'setup_hint')}
    values.update(id=item.id if item else None, name='default', default_provider=lite, require_confirmation=True, created_at=item.created_at if item else None, updated_at=item.updated_at if item else None)
    return values


async def marketplace_response(session: AsyncSession, *, can_manage: bool) -> dict:
    rows = await list_resources(session, 'skills')
    items = []
    for row in rows:
        item = resource_response('skills', row)
        item.update(source='builtin' if row.is_builtin else 'team', source_display='平台内置' if row.is_builtin else '团队自定义', installed=row.is_enabled, can_clone=can_manage, can_edit=can_manage and not row.is_builtin)
        items.append(item)
    return {'summary': {'total': len(items), 'builtin': sum(row.is_builtin for row in rows), 'team': sum(not row.is_builtin for row in rows), 'enabled': sum(row.is_enabled for row in rows)}, 'items': items}
