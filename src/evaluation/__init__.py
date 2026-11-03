"""Retrieval evaluation components and metrics."""

from src.evaluation.metrics import (
    answer_relevancy,
    average_precision,
    context_precision,
    context_precision_judgments,
    context_recall,
    context_recall_claims,
    factual_correctness,
    faithfulness,
    hit_at_k,
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from src.evaluation.dataset import (
    EvaluationDatasetError,
    EvaluationEvidence,
    EvaluationQuestion,
    load_evaluation_dataset,
)
from src.evaluation.retrieval_evaluator import RetrievalEvaluator

__all__ = [
    "EvaluationDatasetError",
    "EvaluationEvidence",
    "EvaluationQuestion",
    "RetrievalEvaluator",
    "answer_relevancy",
    "average_precision",
    "context_precision",
    "context_precision_judgments",
    "context_recall",
    "context_recall_claims",
    "factual_correctness",
    "faithfulness",
    "hit_at_k",
    "load_evaluation_dataset",
    "mean_average_precision",
    "mean_reciprocal_rank",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
]
