"""Own one runtime context per ASGI worker and close it during shutdown."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import contextmanager_in_threadpool

from core.config import Settings
from src.api.services.rag_service import RAGService
from src.runtime import DemoRuntime, open_runtime


logger = logging.getLogger(__name__)
RuntimeFactory = Callable[[Settings], AbstractContextManager[DemoRuntime]]


def create_lifespan(
    settings: Settings, runtime_factory: RuntimeFactory = open_runtime,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Disable ingestion for the API, preserving the existing CLI's behavior.

    Startup fails if corpus/indexes are missing. Operators prepare them with
    scripts.demo before serving. The injected factory enables HTTP integration
    tests without secretly substituting a mock in the production path.
    """
    data = settings.model_dump()
    data["data_pipeline"]["auto_prepare"] = False
    serving_settings = Settings.model_validate(data)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.rag_service = None
        logger.info("rag_api_starting")
        try:
            async with contextmanager_in_threadpool(runtime_factory(serving_settings)) as runtime:
                service = RAGService(runtime, serving_settings)
                app.state.rag_service = service
                logger.info("rag_api_ready corpus_id=%s", service.corpus.corpus_id)
                try:
                    yield
                finally:
                    service.ready = False
                    app.state.rag_service = None
        except Exception as exc:
            logger.error("rag_api_lifecycle_failed error_type=%s", type(exc).__name__)
            logger.debug("rag_api_lifecycle_details", exc_info=True)
            raise
        finally:
            logger.info("rag_api_stopped")

    return lifespan
