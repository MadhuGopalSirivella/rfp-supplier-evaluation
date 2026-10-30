import unittest

from src.scoring import calculate_results


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.criteria = [
            {"criterion_id": 1, "name": "Technical", "weight": 60, "max_score": 10},
            {"criterion_id": 2, "name": "Security", "weight": 40, "max_score": 10},
        ]

    def test_computes_cohort_metrics_and_rank_for_five_suppliers(self):
        suppliers = [
            {
                "supplier_name": f"Supplier {index}",
                "submission_date": f"2026-10-{index:02}",
                "experience_rating": index,
                "scores": {"1": index, "2": 10 - index},
            }
            for index in range(1, 6)
        ]

        results = calculate_results(suppliers, self.criteria)

        self.assertEqual(len(results), 5)
        self.assertEqual([item["final_rank"] for item in results], [1, 2, 3, 4, 5])
        self.assertAlmostEqual(results[0]["absolute_score"], 50)
        self.assertEqual(results[0]["score_coverage"], 100)
        self.assertGreater(results[0]["ppi"], results[-1]["ppi"])

    def test_missing_scores_contribute_zero_and_reduce_coverage(self):
        results = calculate_results(
            [{"supplier_name": "A", "scores": {"1": 8}}], self.criteria
        )

        self.assertEqual(results[0]["absolute_score"], 48)
        self.assertEqual(results[0]["score_coverage"], 60)
        self.assertEqual(results[0]["criteria"][1]["relative_percent"], 100)

    def test_rank_uses_submission_date_then_experience_then_name(self):
        suppliers = [
            {"supplier_name": "Zulu", "submission_date": "2026-01-02", "experience_rating": 8, "scores": {"1": 5, "2": 5}},
            {"supplier_name": "Beta", "submission_date": "2026-01-01", "experience_rating": 2, "scores": {"1": 5, "2": 5}},
            {"supplier_name": "Alpha", "submission_date": "2026-01-01", "experience_rating": 9, "scores": {"1": 5, "2": 5}},
        ]

        results = calculate_results(suppliers, self.criteria)

        self.assertEqual([item["supplier_name"] for item in results], ["Alpha", "Beta", "Zulu"])


if __name__ == "__main__":
    unittest.main()