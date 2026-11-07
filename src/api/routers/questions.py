"""Question endpoint with explicit pipeline outcomes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from src.api.dependencies import get_rag_service
from src.api.schemas.errors import ErrorResponse
from src.api.schemas.questions import QuestionRequest, QuestionResponse
from src.api.services.rag_service import RAGService


router = APIRouter(prefix="/api/v1/questions", tags=["Questions"])


@router.post("", response_model=QuestionResponse, responses={
    422: {"model": ErrorResponse, "description": "Invalid request"},
    502: {"model": QuestionResponse, "description": "Pipeline/provider/verification failed; fallback only"},
    503: {"model": ErrorResponse, "description": "Runtime unavailable or inference capacity exhausted"},
    504: {"model": QuestionResponse, "description": "Pipeline deadline exceeded; fallback only"},
    500: {"model": ErrorResponse, "description": "Unexpected server error"},
})
async def ask_question(
    question: QuestionRequest, request: Request, response: Response,
    service: Annotated[RAGService, Depends(get_rag_service)],
) -> QuestionResponse:
    """Return verified evidence or the orchestrator's explicit fallback.

    A valid but unanswerable question is HTTP 200 / insufficient_evidence.
    Provider/verification failures are 502; pipeline timeouts are 504.
    """
    result = await service.ask(question, request_id=request.state.request_id)
    response.status_code = {"failed": 502, "timed_out": 504}.get(result.status, 200)
    return result
