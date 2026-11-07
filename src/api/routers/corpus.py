"""Metadata about the snapshot currently served by this worker."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import get_rag_service
from src.api.schemas.corpus import CorpusResponse
from src.api.schemas.errors import ErrorResponse
from src.api.services.rag_service import RAGService


router = APIRouter(prefix="/api/v1/corpus", tags=["Corpus"])


@router.get("", response_model=CorpusResponse, responses={503: {"model": ErrorResponse}})
async def get_corpus(service: Annotated[RAGService, Depends(get_rag_service)]) -> CorpusResponse:
    return service.corpus
