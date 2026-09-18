from typing import Literal


ProviderType = Literal['openai_compatible', 'deepseek', 'qwen', 'zhipu', 'kimi']

OPENAI_COMPATIBLE_PROVIDER_TYPES = frozenset({
    'openai_compatible',
    'deepseek',
    'qwen',
    'zhipu',
    'kimi',
})

PRESET_PROVIDER_TYPES = {
    'deepseek': 'deepseek',
    'aliyun_qwen': 'qwen',
    'zhipu_glm': 'zhipu',
    'moonshot_kimi': 'kimi',
}
