import unittest

from scripts.profile_data_coverage import profile_interactions
from src.pipeline import resolve_domain_concepts


class CoverageProfileTests(unittest.TestCase):
    def test_domain_scope_includes_catalog_concepts_by_exact_source_field_suffix(self):
        concepts = [
            {"id": "K_algorithms_计算机科学与技术", "name": "Algorithms"},
            {"id": "K_calculus_数学", "name": "Calculus"},
            {"id": "K_psy_心理学", "name": "Psychology"},
            {"id": "K_unfielded_not-field", "name": "No field"},
            {"id": "K_math_数学-extra", "name": "Not exact suffix"},
        ]

        self.assertEqual(resolve_domain_concepts(concepts, set(), "cs").field_concept_ids,
                         {"K_algorithms_计算机科学与技术"})
        self.assertEqual(resolve_domain_concepts(concepts, set(), "math").field_concept_ids,
                         {"K_calculus_数学"})
        self.assertEqual(resolve_domain_concepts(concepts, set(), "psy").field_concept_ids,
                         {"K_psy_心理学"})

    def test_counts_only_valid_exactly_linked_events_and_preserves_distinct_retakes(self):
        records = [{"log_id": f"e{i}", "user_id": f"u{i // 5}", "problem_id": "p1",
                    "is_correct": i % 2 == 0, "submit_time": f"2025-01-{i + 1:02}T00:00:00Z"}
                   for i in range(10)]
        records.insert(3, records[2].copy())
        records.append({"log_id": "outside", "user_id": "u3", "problem_id": "unmapped",
                        "is_correct": True, "submit_time": "2025-02-01T00:00:00Z"})

        profile = profile_interactions(records, {"cs": {"p1": {"c1", "c2"}},
                                                  "math": {"p1": {"m1"}}}, minimum=7)

        self.assertEqual(profile["cs"]["interactions"], 10)
        self.assertEqual(profile["cs"]["learners"], 2)
        self.assertEqual(profile["cs"]["concepts_with_history"], 2)
        self.assertEqual(profile["cs"]["duplicate_log_ids"], 1)
        self.assertEqual(profile["cs"]["temporal_split_counts"], {"train": 7, "validation": 1, "test": 2})
        self.assertTrue(profile["cs"]["meets_minimum_train_interactions"])
        self.assertEqual(profile["cs"]["learners_with_history_at_test_start"], 2)
        self.assertEqual(profile["cs"]["learners_with_at_least_two_train_events"], 2)
        self.assertEqual(profile["cs"]["max_train_events_for_one_learner"], 5)
        self.assertEqual(profile["cs"]["train_concepts_with_history"], 2)
        self.assertAlmostEqual(profile["cs"]["train_correct_rate"], 4 / 7)
        self.assertEqual(profile["math"]["interactions"], 10)


if __name__ == "__main__":
    unittest.main()
