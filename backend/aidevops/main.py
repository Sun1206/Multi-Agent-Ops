import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aidevops.config import get_settings
from aidevops.database import create_engine, create_session_factory
from aidevops.exceptions import register_exception_handlers
from aidevops.routes import register_routes
from aiops.services.chat_jobs import ChatJobs, recover_interrupted


logger = logging.getLogger(__name__)


def create_app(*, initialize_database: bool = True) -> FastAPI:

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if not initialize_database:
            try:
                yield
            finally:
                await application.state.chat_jobs.close()
            return
        settings = get_settings()
        engine = create_engine(settings)
        application.state.engine = engine
        application.state.session_factory = create_session_factory(engine)
        try:
            await recover_interrupted(application.state.session_factory)
            yield
        finally:
            await application.state.chat_jobs.close()
            await engine.dispose()

    application = FastAPI(title="AI Ops API", version="1.0.0", lifespan=lifespan)
    application.state.chat_jobs = ChatJobs(application)
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
        correlation_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
        request.state.correlation_id = correlation_id
        try:
            response = await call_next(request)
        except Exception as error:
            logger.error("请求处理失败 correlation_id=%s error_type=%s", correlation_id, type(error).__name__)
            response = JSONResponse(status_code=500, content={"detail": "服务器内部错误。"})
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    register_routes(application)
    return application


app = create_app()
