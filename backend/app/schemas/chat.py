# 旧智能助手输入契约与页面上下文归一化，不授予任何运行权限。

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def clean_text(value: Any, limit: int = 180) -> str:
    return ' '.join(str(value or '').strip().split())[:limit]


def clean_mapping(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, item in value.items():
        name = clean_text(key, 64)
        if not name:
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[name] = clean_text(item) if isinstance(item, str) else item
        elif isinstance(item, list):
            result[name] = [clean_text(entry, 80) for entry in item[:8] if clean_text(entry, 80)]
        if len(result) >= 20:
            break
    return result


def normalize_page_context(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    params, query, hints = [clean_mapping(value.get(name)) for name in ('params', 'query', 'hints')]
    merged = {**params, **query, **hints}
    aliases = {
        'environment': ('environment', 'env', 'env_name', 'knowledge_environment'),
        'service': ('service', 'service_name', 'app', 'application', 'system', 'workload'),
        'cluster': ('cluster', 'cluster_name', 'k8s_cluster'),
        'namespace': ('namespace', 'ns'),
        'alert_id': ('alert_id', 'alertId', 'id'),
        'datasource_id': ('datasource_id', 'datasourceId', 'ds_id'),
        'datasource_type': ('datasource_type', 'datasourceType', 'ds_type'),
    }
    for name, keys in aliases.items():
        for key in keys:
            item = merged.get(key)
            item = item[0] if isinstance(item, list) and item else ('' if isinstance(item, list) else item)
            text = clean_text(item)
            if text:
                if not hints.get(name):
                    hints[name] = text
                break
    questions = []
    raw = value.get('suggested_questions')
    if isinstance(raw, list):
        for item in raw:
            text = clean_text(item, 120)
            if text and text not in questions:
                questions.append(text)
            if len(questions) >= 8:
                break
    result = {'page': clean_text(value.get('page') or value.get('name'), 80), 'title': clean_text(value.get('title'), 80), 'route': clean_text(value.get('route') or value.get('path'), 180), 'params': params, 'query': query, 'hints': hints, 'suggested_questions': questions}
    return {key: item for key, item in result.items() if item not in ('', {}, [])}


class CreateSessionInput(BaseModel):
    model_config = ConfigDict(extra='ignore', allow_inf_nan=False, json_schema_extra={'description': '接收旧创建会话载荷，用户归属由服务端赋值。'})
    title: str = Field(default='', max_length=128)
    page_context: Any = Field(default_factory=dict)

    @field_validator('title', mode='before')
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value
