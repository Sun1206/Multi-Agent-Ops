# 读取固定内置能力目录，不导入旧框架或运行任何能力。

import json
from copy import deepcopy
from pathlib import Path


CATALOG = json.loads((Path(__file__).parent / 'catalog' / 'agent_config.json').read_text(encoding='utf-8'))


def action_catalog() -> dict:
    actions = deepcopy(CATALOG['BUILTIN_ACTION_REGISTRY'])
    for item in actions:
        item.update(available=False, available_display='未接入', available_reason='本批仅配置管理，运行处理器尚未接入。', runtime_ready=False)
        item['permission_summary'] = '、'.join(item.get('rbac_permissions', [])) or '无需额外权限'
    summary = {'total': len(actions), 'available': 0}
    for risk in ['read_only', 'draft', 'write', 'execute']:
        summary[risk] = sum(item['risk_level'] == risk for item in actions)
    summary['preflight_required'] = sum(bool(item.get('preflight_required')) for item in actions)
    return {'actions': actions, 'summary': summary}
