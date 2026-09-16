# 实施配置变更、关联校验和同事务审计，不承载任何运行执行逻辑。

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiops.agent_registry import CATALOG
from aidevops.exceptions import BusinessError
from aiops.models import AIOpsAgentConfig, AIOpsMCPServer, AIOpsModelProvider, AIOpsSkill
from rbac.models import Role, User
from aiops.selectors.agent_config import RESOURCE_MODELS, get_resource, provider_hint
from aidevops.config_secrets import encrypt_secret, transform_auth
from eventwall.services import record_event


async def lock_strategies(session: AsyncSession) -> list[AIOpsAgentConfig]:
    return list((await session.scalars(select(AIOpsAgentConfig).order_by(AIOpsAgentConfig.id).with_for_update().execution_options(populate_existing=True))).all())


async def validate_ids(session: AsyncSession, model, identifiers: list[int]) -> list[int]:
    ids = sorted(set(identifiers))
    if ids:
        found = set((await session.scalars(select(model.id).where(model.id.in_(ids)))).all())
        if found != set(ids):
            raise BusinessError('选中的配置对象不存在。')
    return ids


async def validate_skill(session: AsyncSession, values: dict) -> None:
    codes = {item['code'] for item in CATALOG['BUILTIN_ACTION_REGISTRY']}
    if set(values.get('applicable_actions', [])) - codes:
        raise BusinessError('Skill 引用了未登记的 Action。')
    roles = values.get('allowed_role_codes', [])
    if roles:
        found = set((await session.scalars(select(Role.code).where(Role.code.in_(roles)))).all())
        if set(roles) - found:
            raise BusinessError('Skill 引用了不存在的角色。')


async def mutate_resource(session: AsyncSession, kind: str, values: dict, identifier: int | None = None):
    await lock_strategies(session)
    item = await get_resource(session, kind, identifier, lock=True) if identifier is not None else None
    if kind == 'skills':
        await validate_skill(session, values)
        stable = ('slug', 'source_type')
    elif kind == 'mcp-servers':
        stable = ('name', 'server_type', 'endpoint_or_command')
        desired_type = values.get('server_type', item.server_type if item else 'http')
        if desired_type == 'platform_builtin' and not (item and item.is_builtin):
            raise BusinessError('平台内置 MCP 只能由服务端初始化。')
        if 'auth_config' in values:
            values['auth_config'] = transform_auth(values['auth_config'], item.auth_config if item else None)
    else:
        stable = ()
        if 'api_key' in values:
            values['api_key_encrypted'] = encrypt_secret(values.pop('api_key').get_secret_value())
        connection_fields = {'base_url', 'default_model', 'backup_model', 'api_key_encrypted', 'provider_type', 'is_enabled', 'timeout_seconds', 'temperature', 'max_tokens'}
        if item and any(name in values and values[name] != getattr(item, name) for name in connection_fields):
            values.update(last_test_status='unknown', last_test_message='')
    if item and kind in ('providers', 'mcp-servers') and any(values[name] != getattr(item, name) for name in values):
        # MySQL现有时间列只保留整秒；模型及MCP配置修改至少推进一秒，避免改后还原被误判。
        # 诊断不推进此标记；实际诊断时间由审计记录，不修改已应用迁移。
        previous = item.updated_at
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
        values['updated_at'] = max(datetime.now(timezone.utc).replace(microsecond=0), previous + timedelta(seconds=1))
    if item and getattr(item, 'is_builtin', False):
        if any(name in values and values[name] != getattr(item, name) for name in stable):
            raise BusinessError('内置对象的稳定标识和来源不可修改。')
    if item is None:
        item = RESOURCE_MODELS[kind](**values)
        session.add(item)
    else:
        for name, value in values.items():
            setattr(item, name, value)
    await session.flush()
    return item


async def mutate_strategy(session: AsyncSession, values: dict) -> AIOpsAgentConfig:
    rows = await lock_strategies(session)
    if values.get('require_confirmation') is False:
        raise BusinessError('必须保留执行确认保护。')
    if values.get('default_provider_id') is not None:
        provider = await session.get(AIOpsModelProvider, values['default_provider_id'])
        if provider is None or provider_hint(provider):
            raise BusinessError('默认提供商必须启用且配置完整。')
    for name, model in [('enabled_skill_ids', AIOpsSkill), ('enabled_mcp_server_ids', AIOpsMCPServer)]:
        if name in values:
            values[name] = await validate_ids(session, model, values[name])
    item = next((row for row in rows if row.name == 'default'), None)
    if item is None:
        item = AIOpsAgentConfig(name='default')
        session.add(item)
    for name, value in values.items():
        setattr(item, name, value)
    item.require_confirmation = True
    await session.flush()
    return item


async def remove_resource(session: AsyncSession, kind: str, identifier: int) -> None:
    rows = await lock_strategies(session)
    item = await get_resource(session, kind, identifier, lock=True)
    if getattr(item, 'is_builtin', False):
        raise BusinessError('内置配置不可删除。')
    for row in rows:
        if kind == 'providers' and row.default_provider_id == identifier:
            row.default_provider_id = None
        elif kind == 'skills':
            row.enabled_skill_ids = [value for value in row.enabled_skill_ids if value != identifier]
        elif kind == 'mcp-servers':
            row.enabled_mcp_server_ids = [value for value in row.enabled_mcp_server_ids if value != identifier]
    await session.flush()
    await session.execute(delete(RESOURCE_MODELS[kind]).where(RESOURCE_MODELS[kind].id == identifier).execution_options(synchronize_session=False))


async def clone_skill(session: AsyncSession, identifier: int, values: dict):
    from aiops.schemas.agent_config import SkillPatch

    await lock_strategies(session)
    source = await get_resource(session, 'skills', identifier, lock=True)
    data = {name: deepcopy(getattr(source, name)) for name in SkillPatch.model_fields}
    suffix = uuid4().hex[:12]
    data['name'] = values.get('name', source.name[:100] + ' 团队版-' + suffix)
    data['slug'] = values.get('slug', source.slug[:100] + '-team-' + suffix)
    item = AIOpsSkill(**data, is_builtin=False)
    session.add(item)
    await session.flush()
    return item


async def audit_config(session: AsyncSession, request: Request, actor: User, action: str, kind: str, identifier: int, fields: list[str]) -> None:
    await record_event(session, actor=actor, method=request.method, path=request.url.path, ip_address=request.client.host if request.client else '', correlation_id=getattr(request.state, 'correlation_id', ''), action=action, title='智能体配置变更', resource_type=kind, resource_id=str(identifier), metadata={'changed_fields': sorted(fields)}, module='aiops', category='configuration')


async def bootstrap_agent_catalog(session: AsyncSession) -> None:
    await lock_strategies(session)
    if await session.scalar(select(AIOpsAgentConfig.id).where(AIOpsAgentConfig.name == 'default')) is None:
        session.add(AIOpsAgentConfig(name='default', require_confirmation=True))
    for definition in CATALOG['BUILTIN_SKILLS']:
        if await session.scalar(select(AIOpsSkill.id).where(AIOpsSkill.slug == definition['slug'])) is None:
            session.add(AIOpsSkill(**deepcopy(definition), is_builtin=True))
    if await session.scalar(select(AIOpsMCPServer.id).where(AIOpsMCPServer.name == '平台只读工具目录')) is None:
        session.add(AIOpsMCPServer(name='平台只读工具目录', server_type='platform_builtin', endpoint_or_command='platform://readonly', description='仅声明平台能力，运行服务尚未接入。', is_builtin=True, is_enabled=False))
    await session.flush()
