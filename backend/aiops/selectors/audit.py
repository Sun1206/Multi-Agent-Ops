from collections import Counter
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiops.models import AIOpsChatMessage, AIOpsModelInvocation, AIOpsModelProvider, AIOpsToolInvocation
from aiops.schemas.audit import ResolvedAuditRange


MONEY_STEP = Decimal('0.000001')


def _time_conditions(model, window: ResolvedAuditRange) -> list:
    conditions = []
    if window.start is not None:
        conditions.append(model.created_at >= window.start)
    if window.end is not None:
        conditions.append(model.created_at <= window.end)
    return conditions


def _money(value) -> float:
    return float(Decimal(str(value or 0)).quantize(MONEY_STEP, rounding=ROUND_HALF_UP))


def _trace_distribution(messages: list[AIOpsChatMessage], field: str) -> list[dict]:
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for message in messages:
        metadata = message.metadata_data if isinstance(message.metadata_data, dict) else {}
        traces = metadata.get(field)
        if not isinstance(traces, list):
            continue
        for trace in traces:
            if not isinstance(trace, dict):
                continue
            key = trace.get('key')
            label = trace.get('label')
            if not isinstance(key, str) or not key.strip() or not isinstance(label, str) or not label.strip():
                continue
            key = key.strip()[:128]
            counts[key] += 1
            labels.setdefault(key, label.strip()[:128])
    rows = ({'key': key, 'label': labels[key], 'count': count} for key, count in counts.items())
    return sorted(rows, key=lambda row: (-row['count'], row['key']))[:100]


async def build_overview(session: AsyncSession, window: ResolvedAuditRange) -> dict:
    tool_statement = (
        select(AIOpsToolInvocation.tool_name, func.count(AIOpsToolInvocation.id))
        .where(*_time_conditions(AIOpsToolInvocation, window))
        .group_by(AIOpsToolInvocation.tool_name)
    )
    tool_rows = [
        {'key': name, 'label': name, 'count': count}
        for name, count in (await session.execute(tool_statement)).all()
        if isinstance(name, str) and name
    ]
    tool_rows.sort(key=lambda row: (-row['count'], row['key']))
    message_statement = select(AIOpsChatMessage).where(
        AIOpsChatMessage.role == AIOpsChatMessage.ROLE_ASSISTANT,
        *_time_conditions(AIOpsChatMessage, window),
    )
    messages = list((await session.scalars(message_statement)).all())
    return {
        'invocation_distribution': {
            'mcp_tools': tool_rows[:100],
            'skills': _trace_distribution(messages, 'skill_traces'),
            'actions': _trace_distribution(messages, 'action_traces'),
        },
    }


async def build_costs(session: AsyncSession, window: ResolvedAuditRange) -> dict:
    model_statement = (
        select(
            func.coalesce(AIOpsModelProvider.name, '已删除提供商'),
            AIOpsModelInvocation.estimated_cost_currency,
            func.count(AIOpsModelInvocation.id),
            func.coalesce(func.sum(AIOpsModelInvocation.total_tokens), 0),
            func.coalesce(func.sum(AIOpsModelInvocation.estimated_cost_usd), 0),
            func.coalesce(func.avg(AIOpsModelInvocation.latency_ms), 0),
        )
        .outerjoin(AIOpsModelProvider, AIOpsModelProvider.id == AIOpsModelInvocation.provider_id)
        .where(*_time_conditions(AIOpsModelInvocation, window))
        .group_by(AIOpsModelProvider.name, AIOpsModelInvocation.estimated_cost_currency)
    )
    model_rows = (await session.execute(model_statement)).all()
    by_provider = []
    model_latency_total = 0.0
    for provider, currency, calls, tokens, cost, latency in model_rows:
        model_latency_total += float(latency) * calls
        by_provider.append({
            'provider': provider,
            'cost_currency': currency,
            'calls': calls,
            'tokens': int(tokens),
            'estimated_cost_usd': _money(cost),
            'avg_latency_ms': round(float(latency)),
        })
    by_provider.sort(key=lambda row: (-row['calls'], row['provider'], row['cost_currency']))
    currencies: dict[str, dict] = {}
    for row in by_provider:
        aggregate = currencies.setdefault(row['cost_currency'], {'currency': row['cost_currency'], 'calls': 0, 'tokens': 0, 'estimated_cost_usd': Decimal(0)})
        aggregate['calls'] += row['calls']
        aggregate['tokens'] += row['tokens']
        aggregate['estimated_cost_usd'] += Decimal(str(row['estimated_cost_usd']))
    by_currency = [
        {**row, 'estimated_cost_usd': _money(row['estimated_cost_usd'])}
        for _, row in sorted(currencies.items())
    ]
    total_calls = sum(row['calls'] for row in by_provider)
    total_tokens = sum(row['tokens'] for row in by_provider)
    single_currency = by_currency[0] if len(by_currency) == 1 else None

    tool_statement = (
        select(
            AIOpsToolInvocation.tool_name,
            func.count(AIOpsToolInvocation.id),
            func.coalesce(func.avg(AIOpsToolInvocation.latency_ms), 0),
        )
        .where(*_time_conditions(AIOpsToolInvocation, window))
        .group_by(AIOpsToolInvocation.tool_name)
    )
    tool_rows = (await session.execute(tool_statement)).all()
    by_tool = [{'tool_name': name, 'calls': calls, 'avg_latency_ms': round(float(latency))} for name, calls, latency in tool_rows]
    by_tool.sort(key=lambda row: (-row['calls'], row['tool_name']))
    tool_calls = sum(row['calls'] for row in by_tool)
    tool_latency = sum(float(latency) * calls for _, calls, latency in tool_rows)
    return {
        'model': {
            'total_calls': total_calls,
            'total_tokens': total_tokens,
            'estimated_cost_usd': single_currency['estimated_cost_usd'] if single_currency else 0,
            'cost_currency': single_currency['currency'] if single_currency else '',
            'avg_latency_ms': round(model_latency_total / total_calls) if total_calls else 0,
            'by_currency': by_currency,
            'by_provider': by_provider,
        },
        'tools': {
            'total_calls': tool_calls,
            'avg_latency_ms': round(tool_latency / tool_calls) if tool_calls else 0,
            'by_tool': by_tool[:100],
        },
    }
