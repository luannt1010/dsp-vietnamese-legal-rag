"""Cheap process/runtime probes; no inference or database writes."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from core.schemas.base import ContractModel
from src.api.dependencies import get_rag_service
from src.api.schemas.errors import ErrorResponse
from src.api.services.rag_service import RAGService


class HealthResponse(ContractModel):
    status: Literal["alive", "ready"]


router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="alive")


@router.get("/ready", response_model=HealthResponse, responses={503: {"model": ErrorResponse}})
async def readiness(service: Annotated[RAGService, Depends(get_rag_service)]) -> HealthResponse:
    """Runtime loaded and accepting work; not a live dependency connectivity test."""
    return HealthResponse(status="ready")
