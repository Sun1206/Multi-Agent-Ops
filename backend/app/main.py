import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers.auth import router as auth_router
from app.api.routers.module_settings import router as module_router
from app.api.routers.users import router as users_router
from app.api.routers.roles import router as roles_router
from app.api.routers.groups import router as groups_router
from app.api.routers.permissions import router as permissions_router
from app.core.config import get_settings
from app.core.database import create_engine, create_session_factory
from app.core.exceptions import register_exception_handlers


logger = logging.getLogger(__name__)


def create_app(*, initialize_database: bool = True) -> FastAPI:
    """装配 FastAPI 路由、中间件和可控的异步数据库生命周期。"""

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        """启动时创建连接池，关闭时释放全部数据库连接。"""
        if not initialize_database:
            yield
            return
        settings = get_settings()
        engine = create_engine(settings)
        application.state.engine = engine
        application.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    application = FastAPI(title="AI Ops API", version="1.0.0", lifespan=lifespan)
    register_exception_handlers(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        """为每个请求生成关联 ID，并回传给前端用于定位错误。"""
        correlation_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
        request.state.correlation_id = correlation_id
        try:
            response = await call_next(request)
        except Exception as error:
            logger.error("请求处理失败 correlation_id=%s error_type=%s", correlation_id, type(error).__name__)
            response = JSONResponse(status_code=500, content={"detail": "服务器内部错误。"})
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    application.include_router(auth_router)
    application.include_router(module_router)
    application.include_router(users_router)
    application.include_router(roles_router)
    application.include_router(groups_router)
    application.include_router(permissions_router)
    return application


app = create_app()
