"""One HTTP error envelope for validation, availability and unexpected errors."""

from pydantic import Field

from core.schemas.base import ContractModel


class ValidationIssue(ContractModel):
    location: list[str | int]
    code: str
    message: str


class ErrorDetail(ContractModel):
    code: str
    message: str
    issues: list[ValidationIssue] = Field(default_factory=list)


class ErrorResponse(ContractModel):
    request_id: str
    error: ErrorDetail
