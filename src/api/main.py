"""FastAPI application factory; importing this module does not load models."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import Settings
from src.api.exception_handlers import register_exception_handlers
from src.api.lifespan import RuntimeFactory, create_lifespan
from src.api.middleware import RequestContextMiddleware
from src.api.routers import corpus, health, questions
from src.api.settings import load_api_settings
from src.runtime import open_runtime


def create_app(
    settings: Settings | None = None, *, runtime_factory: RuntimeFactory = open_runtime,
) -> FastAPI:
    """Compose HTTP concerns around the existing injectable RAG runtime."""
    settings = settings if settings is not None else load_api_settings()
    application = FastAPI(
        title="Vietnamese Legal RAG API", version="1.0.0",
        description="Hỏi đáp theo snapshot pháp luật, kiểm chứng trích dẫn trước khi trả kết quả.",
        lifespan=create_lifespan(settings, runtime_factory),
    )
    application.state.settings = settings
    application.state.rag_service = None
    register_exception_handlers(application)
    application.include_router(health.router)
    application.include_router(questions.router)
    application.include_router(corpus.router)
    application.add_middleware(RequestContextMiddleware)
    if settings.api.cors_origins:
        application.add_middleware(
            CORSMiddleware, allow_origins=list(settings.api.cors_origins),
            allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
            expose_headers=["X-Request-ID", "Retry-After"],
        )
    return application


app = create_app()
