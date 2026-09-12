from pydantic import BaseModel


class DetailResponse(BaseModel):
    """统一返回可安全展示的错误详情。"""

    detail: str


class SuccessResponse(BaseModel):
    """统一返回简单操作是否成功。"""

    success: bool = True
