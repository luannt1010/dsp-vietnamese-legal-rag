"""Deterministic configured routing, without assuming an unfinished intent taxonomy."""

from collections.abc import Mapping

from pydantic import JsonValue

from core.config.settings import RetrievalSettings
from core.interfaces import BaseRetrievalRouter
from core.schemas import RetrievalRouteRequest, RetrievalStrategy
from src.retrieval.common import validate_filters


class RetrievalRouter(BaseRetrievalRouter):
    def __init__(
        self, settings: RetrievalSettings | None = None,
        *, intent_overrides: Mapping[str, Mapping[str, JsonValue]] | None = None,
    ):
        self.settings = settings or RetrievalSettings()
        self._strategies: dict[str, RetrievalStrategy] = {}
        baseline = self.settings.default_strategy().model_dump()
        for intent, override in (intent_overrides or {}).items():
            self._strategies[intent] = self.settings.validate_strategy(
                RetrievalStrategy.model_validate({
                    **baseline, "reason": f"Configured policy for intent {intent}", **override,
                }),
            )

    def route(self, request: RetrievalRouteRequest) -> RetrievalStrategy:
        validate_filters(request.filters)
        strategy = self._strategies.get(request.intent, self.settings.default_strategy())
        return self.settings.validate_strategy(strategy)
