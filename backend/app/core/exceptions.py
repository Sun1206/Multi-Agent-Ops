from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError


class BusinessError(ValueError):
    """表示可安全展示给客户端的业务输入错误。"""


def register_exception_handlers(application: FastAPI) -> None:
    """注册统一错误响应，避免 SQL 参数和校验输入泄露到前端。"""

    @application.exception_handler(BusinessError)
    async def business_error_handler(request: Request, error: BusinessError) -> JSONResponse:
        """把受控业务错误转换为 400 detail 响应。"""
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @application.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, error: IntegrityError) -> JSONResponse:
        """把数据库唯一性或状态冲突转换为不含 SQL 参数的 409 响应。"""
        return JSONResponse(status_code=409, content={"detail": "数据存在唯一性或关联状态冲突。"})

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
        """把字段校验失败转换为 422，并且不回显密码等原始输入。"""
        return JSONResponse(status_code=422, content={"detail": "请求字段校验失败。"})
