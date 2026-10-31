import unittest

from src.evaluation.metrics import ndcg_at_k, recall_at_k, reciprocal_rank


class EvaluationMetricsTests(unittest.TestCase):
    def test_recall_at_k(self) -> None:
        self.assertEqual(recall_at_k(["a", "b", "c"], {"b", "d"}, 2), 0.5)

    def test_reciprocal_rank_uses_first_unique_relevant_hit(self) -> None:
        self.assertEqual(reciprocal_rank(["x", "x", "b"], {"b"}), 0.5)
        self.assertEqual(reciprocal_rank(["x", "y"], {"b"}, k=2), 0.0)

    def test_ndcg_is_normalized_and_rewards_earlier_relevant_hits(self) -> None:
        self.assertEqual(ndcg_at_k(["a", "b"], {"a", "b"}, 2), 1.0)
        self.assertLess(ndcg_at_k(["x", "a"], {"a"}, 2), 1.0)

    def test_invalid_inputs_raise_value_error(self) -> None:
        with self.assertRaises(ValueError):
            recall_at_k(["a"], set(), 1)
        with self.assertRaises(ValueError):
            ndcg_at_k(["a"], {"a"}, 0)


if __name__ == "__main__":
    unittest.main()
