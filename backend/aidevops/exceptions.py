from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError


class BusinessError(ValueError):
    pass


def register_exception_handlers(application: FastAPI) -> None:

    @application.exception_handler(BusinessError)
    async def business_error_handler(request: Request, error: BusinessError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @application.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, error: IntegrityError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "数据存在唯一性或关联状态冲突。"})

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "请求字段校验失败。"})
