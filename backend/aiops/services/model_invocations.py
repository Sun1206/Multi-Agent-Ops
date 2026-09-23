from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from aiops.models import AIOpsModelInvocation


MAX_COUNTER = 2_000_000_000
MONEY_STEP = Decimal('0.000001')
SUMMARY_FIELDS = {
    'message_count',
    'content_length',
    'prompt_length',
    'input_length',
    'round',
    'tool_count',
}


def _counter(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_COUNTER:
        return None
    return value


def _decimal(value) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)
    return result if result.is_finite() and result >= 0 else Decimal(0)


def _model_id(value, fallback: str) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized and len(normalized) <= 128 and all(32 <= ord(character) < 127 for character in value):
            return normalized
    return fallback[:128]


def _safe_request_summary(summary: object) -> dict:
    if not isinstance(summary, dict):
        return {}
    return {
        key: value
        for key, value in summary.items()
        if key in SUMMARY_FIELDS and _counter(value) is not None
    }


def invocation_values(*, provider: dict, session_id: int, message_id: int, username: str, latency_ms: int, result: object, status: str, termination: str, request_summary: dict) -> dict:
    response = result if isinstance(result, dict) else {}
    usage = response.get('usage') if isinstance(response.get('usage'), dict) else {}
    prompt_tokens = _counter(usage.get('prompt_tokens'))
    completion_tokens = _counter(usage.get('completion_tokens'))
    has_usage = prompt_tokens is not None and completion_tokens is not None
    if not has_usage:
        prompt_tokens = completion_tokens = 0
    total_tokens = prompt_tokens + completion_tokens
    input_price = _decimal(provider.get('input_token_price_per_1m'))
    output_price = _decimal(provider.get('output_token_price_per_1m'))
    cost = ((Decimal(prompt_tokens) * input_price + Decimal(completion_tokens) * output_price) / Decimal(1_000_000)).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)
    requested_model = _model_id(provider.get('default_model'), '')
    currency = str(provider.get('price_currency') or 'USD').upper()
    if len(currency) != 3 or not currency.isalpha():
        currency = 'USD'
    return {
        'provider_id': provider.get('id'),
        'session_id': session_id,
        'message_id': message_id,
        'username': str(username or '')[:64],
        'purpose': AIOpsModelInvocation.PURPOSE_CHAT_PLANNING,
        'requested_model': requested_model,
        'resolved_model': _model_id(response.get('model'), requested_model),
        'status': AIOpsModelInvocation.STATUS_SUCCESS if status == 'success' else AIOpsModelInvocation.STATUS_FAILED,
        'latency_ms': max(0, min(int(latency_ms), MAX_COUNTER)),
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'total_tokens': total_tokens,
        'estimated_cost_usd': cost,
        'estimated_cost_currency': currency,
        'request_summary': _safe_request_summary(request_summary),
        'response_summary': {'termination': termination if termination in {'completed', 'tool_calls', 'failure', 'cancelled'} else 'failure', 'has_usage': has_usage},
    }


def model_invocation(**kwargs) -> AIOpsModelInvocation:
    return AIOpsModelInvocation(**invocation_values(**kwargs))
