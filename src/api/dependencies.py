"""Resolve the worker-local service; never create runtimes inside a request."""

from fastapi import Request

from src.api.services.rag_service import RAGService, ServiceUnavailableError


async def get_rag_service(request: Request) -> RAGService:
    service = request.app.state.rag_service
    if service is None or not service.ready:
        raise ServiceUnavailableError
    return service
