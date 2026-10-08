# 记录本次实际选择的策略和Skill快照，不从历史文本推断命中或执行结果。

from copy import deepcopy


# 在发送模型请求前保存固定展示字段，不包含提示词、查询参数或提供商凭据。
def trace_snapshot(action, skills, allowed_names):
    action = action or {}
    code, label = action.get('code', ''), action.get('display_name', '')
    skill_rows = [{
        'key': skill.slug, 'label': skill.name, 'category': skill.category,
        'risk_level': skill.risk_level, 'status': 'matched',
        'hit_reason': 'action_matched', 'action_code': code,
        'action_display_name': label, 'applicable_actions': list(skill.applicable_actions or []),
        'allowed_tools': sorted(set(skill.builtin_tools or []) | set(skill.recommended_tools or [])),
    } for skill in skills]
    action_rows = [{
        'key': code, 'label': label or code, 'risk_level': action.get('risk_level', ''),
        'allowed_tools': list(allowed_names), 'skills': [skill.slug for skill in skills],
        'skill_names': [skill.name for skill in skills],
        'status': 'matched' if allowed_names else 'blocked', 'draft_generated': False,
    }] if code else []
    return {'skill_traces': skill_rows, 'action_traces': action_rows}


# 用实际工具调用填充本轮使用信息；普通分析不会被标成已执行的写操作。
def completed_traces(snapshot, tool_calls, status):
    result = deepcopy(snapshot)
    used = {item['name'] for item in (tool_calls or []) if isinstance(item, dict) and isinstance(item.get('name'), str)}
    for skill in result['skill_traces']:
        skill['used_tools'] = sorted(used.intersection(skill['allowed_tools']))
        if skill['used_tools']:
            skill.update(status='called', hit_reason='action_called')
    for action in result['action_traces']:
        if status == 'failed':
            action['status'] = 'failed'
    return result
