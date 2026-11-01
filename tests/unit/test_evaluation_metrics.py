import unittest
from typing import Literal, cast

from src.evaluation.metrics import (
    answer_relevancy,
    average_precision,
    context_precision,
    context_recall,
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


class EvaluationMetricsTests(unittest.TestCase):
    def test_recall_at_k(self) -> None:
        self.assertEqual(recall_at_k(["a", "b", "c"], {"b", "d"}, 2), 0.5)

    def test_precision_at_k_uses_k_as_denominator(self) -> None:
        self.assertEqual(precision_at_k(["a", "b"], {"b"}, 4), 0.25)

    def test_average_precision_and_map(self) -> None:
        self.assertAlmostEqual(average_precision(["a", "x", "b"], {"a", "b", "c"}), 5 / 9)
        self.assertAlmostEqual(
            mean_average_precision(
                [["a", "x", "b"], ["x", "c"]],
                [{"a", "b", "c"}, {"c"}],
            ),
            (5 / 9 + 0.5) / 2,
        )

    def test_reciprocal_rank_uses_first_unique_relevant_hit(self) -> None:
        self.assertEqual(reciprocal_rank(["x", "x", "b"], {"b"}), 0.5)
        self.assertEqual(reciprocal_rank(["x", "y"], {"b"}, k=2), 0.0)

    def test_mrr_and_hit_at_k(self) -> None:
        self.assertEqual(
            mean_reciprocal_rank([["x", "a"], ["b"]], [{"a"}, {"c"}]),
            0.25,
        )
        self.assertEqual(hit_at_k(["x", "a"], {"a"}, 2), 1.0)
        self.assertEqual(hit_at_k(["x", "y"], {"a"}, 2), 0.0)

    def test_context_precision_and_recall_from_reference_ids(self) -> None:
        self.assertAlmostEqual(
            context_precision(["noise", "relevant-a", "relevant-b"], {"relevant-a", "relevant-b"}),
            (1 / 2 + 2 / 3) / 2,
        )
        self.assertEqual(
            context_recall(["noise", "relevant-a"], {"relevant-a", "relevant-b"}),
            0.5,
        )
        self.assertEqual(context_precision(["noise"], {"relevant-a"}), 0.0)

    def test_answer_quality_metrics_aggregate_external_judgments(self) -> None:
        self.assertEqual(faithfulness([True, False, True]), 2 / 3)
        self.assertEqual(answer_relevancy([0.8, 0.6]), 0.7)
        self.assertEqual(
            factual_correctness(
                [True, False, True],
                [True, True, False],
                mode="precision",
            ),
            2 / 3,
        )
        self.assertEqual(
            factual_correctness(
                [True, False, True],
                [True, True, False],
                mode="recall",
            ),
            2 / 3,
        )
        self.assertEqual(
            factual_correctness([False], [True], mode="f1"),
            0.0,
        )

    def test_ndcg_is_normalized_and_rewards_earlier_relevant_hits(self) -> None:
        self.assertEqual(ndcg_at_k(["a", "b"], {"a", "b"}, 2), 1.0)
        self.assertLess(ndcg_at_k(["x", "a"], {"a"}, 2), 1.0)

    def test_invalid_inputs_raise_value_error(self) -> None:
        with self.assertRaises(ValueError):
            recall_at_k(["a"], set(), 1)
        with self.assertRaises(ValueError):
            ndcg_at_k(["a"], {"a"}, 0)
        with self.assertRaises(ValueError):
            faithfulness([])
        with self.assertRaises(ValueError):
            answer_relevancy([float("nan")])
        with self.assertRaises(ValueError):
            factual_correctness(
                [True],
                [False],
                mode=cast(Literal["precision", "recall", "f1"], "unsupported"),
            )


if __name__ == "__main__":
    unittest.main()
