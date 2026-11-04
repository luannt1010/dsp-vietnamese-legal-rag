"""Separate experiment configuration; reuse the production Settings validator."""

from pathlib import Path

from pydantic import Field, model_validator
import yaml

from core.config import Settings
from core.config.settings import ConfigModel
from core.schemas.base import NonEmptyString, PositiveInt, NonNegativeInt
from core.schemas.orchestration import PipelineRunOptions


class Experiment(ConfigModel):
    id: NonEmptyString = Field(pattern=r"^[A-Za-z0-9_-]+$")
    use_graph: bool
    use_rerank: bool
    max_iterations: PositiveInt = 1


class BenchmarkConfig(ConfigModel):
    version: int = Field(default=1, ge=1, le=1)
    repeats: PositiveInt = 3
    seed: int = 42
    warmup_queries: NonNegativeInt = 1
    replay_analysis: bool = False
    ranking_k: PositiveInt = 20
    context_top_k: PositiveInt = 5
    candidate_k: PositiveInt = 20
    ks: tuple[PositiveInt, ...] = (5, 10, 20)
    bootstrap_samples: PositiveInt = 2000
    hardware_notes: NonEmptyString = "Record CPU/GPU/RAM and model quantization before the run"
    experiments: tuple[Experiment, ...]

    @model_validator(mode="after")
    def check_matrix(self):
        if not self.experiments or len({e.id for e in self.experiments}) != len(self.experiments):
            raise ValueError("experiment IDs must be nonempty and unique")
        if not self.context_top_k <= self.ranking_k <= self.candidate_k:
            raise ValueError("require context_top_k <= ranking_k <= candidate_k")
        if not self.ks or len(set(self.ks)) != len(self.ks) or max(self.ks) > self.ranking_k:
            raise ValueError("ks must be unique and fit inside the retained ranking")
        return self

    def settings_for(self, base: Settings, experiment: Experiment) -> Settings:
        data = base.model_dump()
        data["retrieval"].update(use_bm25=True, use_vector=True,
                                 use_graph=experiment.use_graph, use_rerank=experiment.use_rerank,
                                 top_k=self.context_top_k, candidate_k=self.candidate_k)
        data["pipeline"]["max_iterations"] = experiment.max_iterations
        # Benchmark queries must never silently download a new corpus or rebuild indexes.
        data["data_pipeline"]["auto_prepare"] = False
        settings = Settings.model_validate(data)
        settings.retrieval.validate_strategy(settings.retrieval.default_strategy().model_copy(
            update={"top_k": self.ranking_k}))
        return settings

    def run_options(self) -> PipelineRunOptions:
        return PipelineRunOptions(ranking_k=self.ranking_k, context_top_k=self.context_top_k,
                                  allow_strategy_changes=False)


def load_config(path: Path) -> BenchmarkConfig:
    return BenchmarkConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8-sig")))
