from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

from aidevops.types import ensure_utc


class ModuleToggle(BaseModel):
    model_config = {'json_schema_extra': {'description': "表示一个可选模块的目标启用状态。"}}

    code: str = Field(min_length=1, max_length=64)
    enabled: bool


class ModuleSettingsBody(BaseModel):
    model_config = {'json_schema_extra': {'description': "兼容前端使用 `modules` 包裹列表的更新结构。"}}

    modules: list[ModuleToggle]


class ModuleSettingsList(RootModel[list[ModuleToggle]]):
    model_config = {'json_schema_extra': {'description': "兼容前端直接提交模块列表的更新结构。"}}


class ModuleSettingResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True, json_schema_extra={'description': '输出固定目录信息和数据库中的开关状态。'})
    code: str
    title: str
    description: str
    required: bool
    sort_order: int
    enabled: bool
    updated_by: str
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class ModuleUpdateResponse(BaseModel):
    model_config = {'json_schema_extra': {'description': "返回模块设置写入结果和更新后的完整目录。"}}

    success: bool = True
    data: list[ModuleSettingResponse]


def normalize_module_payload(
    payload: list[ModuleToggle | dict[str, object]] | ModuleSettingsBody,
) -> list[ModuleToggle]:
    values = payload.modules if isinstance(payload, ModuleSettingsBody) else payload
    return [item if isinstance(item, ModuleToggle) else ModuleToggle.model_validate(item) for item in values]
