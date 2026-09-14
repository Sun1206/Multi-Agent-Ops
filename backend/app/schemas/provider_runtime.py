from typing import Literal

from pydantic import BaseModel, Field


# 连接测试公开载荷，不包含模型正文、API Key、密文或原始网络错误。
class ConnectionResult(BaseModel):
    status: Literal['success', 'failed']
    message: str
    resolved_model: str | None = None


# 目录仅公开经清洗的模型ID，不原样传递供应商的其他字段。
class CatalogModel(BaseModel):
    id: str = Field(min_length=1, max_length=128)


# 区分请求模型与供应商标识，并明确文本验证及工具声明验证状态。
class ModelRecommendation(BaseModel):
    model: str
    requested_model: str
    verified: bool
    supports_tool_calling: bool
    message: str


# 沿用旧页面目录字段；回退目录和推荐结果仅返回，不自动修改提供商。
class ModelCatalogResult(BaseModel):
    models: list[CatalogModel]
    count: int
    recommendation: ModelRecommendation | None = None
    probe_candidates: list[str] = Field(default_factory=list)
    probe_error: str = ''
    catalog_error: str = ''
    fallback_used: bool = False
