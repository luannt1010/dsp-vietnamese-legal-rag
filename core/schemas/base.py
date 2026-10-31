"""Validation primitives shared by all public data contracts."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class ContractModel(BaseModel):
    """Reject undeclared fields so contract typos fail at module boundaries."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
