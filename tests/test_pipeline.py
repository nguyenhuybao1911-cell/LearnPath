import unittest
import csv
import gzip
import json
import tempfile
from pathlib import Path

from src.pipeline import (
    _clean_payload,
    parse_prerequisites,
    resolve_domain_concepts,
    split_for_index,
    split_for_timestamp,
)


class PipelineTests(unittest.TestCase):
    def test_resolves_prerequisite_names_to_exact_domain_ids(self):
        concepts = [
            {"id": "K_sort_cs", "name": "sort", "field": "计算机科学与技术"},
            {"id": "K_sort_math", "name": "sort", "field": "数学"},
            {"id": "K_unique_not-field", "name": "unique", "field": "not-field"},
            {"id": "K_unique_other_field", "name": "other", "field": "数学"},
            {"id": "K_ambiguous_a", "name": "ambiguous", "field": "物理学"},
            {"id": "K_ambiguous_b", "name": "ambiguous", "field": "数学"},
        ]

        result = resolve_domain_concepts(concepts, {"sort", "unique", "other", "ambiguous"}, "cs")

        self.assertEqual(result.name_to_id["sort"], "K_sort_cs")
        self.assertEqual(result.name_to_id["unique"], "K_unique_not-field")
        self.assertNotIn("ambiguous", result.name_to_id)
        self.assertNotIn("other", result.name_to_id)
        self.assertEqual({row["reason"] for row in result.rejected},
                         {"ambiguous_concept_name", "concept_field_mismatch"})

    def test_minus_one_is_unannotated_and_probability_arrays_use_positive_class(self):
        result = parse_prerequisites([
            {"c1": "a", "c2": "b", "ground_truth": -1,
             "text_predict": [0.2, 0.8], "graph_predict": [0.3, 0.7]},
        ], {"a", "b"})

        self.assertEqual(result.rows[0]["ground_truth"], None)
        self.assertEqual(result.rows[0]["annotated"], False)
        self.assertEqual(result.rows[0]["text_predict"], 0.8)
        self.assertEqual(result.rows[0]["graph_predict"], 0.7)
        self.assertEqual(result.rejected, [])

    def test_keeps_ground_truth_separate_and_logs_cycles(self):
        rows = [
            {"c1": "a", "c2": "b", "ground_truth": 1, "text_predict": 0.9, "graph_predict": 0.8},
            {"c1": "b", "c2": "c", "ground_truth": 1, "text_predict": 0.8, "graph_predict": 0.7},
            {"c1": "c", "c2": "a", "ground_truth": 1, "text_predict": 0.5, "graph_predict": 0.4},
            {"c1": "c", "c2": "b", "ground_truth": 0, "text_predict": 0.7, "graph_predict": 0.6},
            {"c1": "a", "c2": "c", "text_predict": 0.6, "graph_predict": 0.5},
        ]
        result = parse_prerequisites(rows, {"a", "b", "c"})
        self.assertEqual({(edge.prerequisite, edge.concept) for edge in result.edges}, {("a", "b"), ("b", "c")})
        self.assertEqual([x["ground_truth"] for x in result.rows], [1, 1, 0, None])
        self.assertEqual(result.rows[-1]["annotated"], False)
        self.assertEqual(result.rejected[0]["reason"], "would_create_cycle")

    def test_time_split_boundaries_are_stable_and_cover_each_row(self):
        n = 100
        labels = [split_for_index(i, n, .7, .15) for i in range(n)]
        self.assertEqual(labels[:70], ["train"] * 70)
        self.assertEqual(labels[70:85], ["validation"] * 15)
        self.assertEqual(labels[85:], ["test"] * 15)

    def test_equal_timestamps_are_never_split_across_temporal_sets(self):
        self.assertEqual(split_for_timestamp("2025-01-02T00:00:00.000000+00:00",
                                             "2025-01-02T00:00:00.000000+00:00",
                                             "2025-01-03T00:00:00.000000+00:00"), "validation")

    def test_pipeline_preserves_retakes_and_is_idempotent_on_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            for subdir in ("entities", "relations", "prerequisites"):
                (raw / subdir).mkdir(parents=True)
            (raw / "entities/concept.json").write_text(json.dumps([
                {"id": "cA", "name": "外部中断"}, {"id": "cB", "name": "Beta"},
            ]), encoding="utf-8")
            (raw / "prerequisites/cs.json").write_text(json.dumps([
                {"c1": "cA", "c2": "cB", "ground_truth": 1, "text_predict": .7, "graph_predict": .8},
            ]), encoding="utf-8")
            (raw / "relations/concept-problem.txt").write_text("cA\tp1\ncB\tp1\n", encoding="utf-8")
            (raw / "relations/user-problem.json").write_text(json.dumps([
                {"log_id": "e1", "user_id": "u", "problem_id": "p1", "is_correct": True, "attempts": 7, "submit_time": "2025-01-01T00:00:00Z"},
                {"log_id": "e2", "user_id": "u", "problem_id": "p1", "is_correct": False, "attempts": 1, "submit_time": "2025-01-02T00:00:00Z"},
                {"log_id": "e2", "user_id": "u", "problem_id": "p1", "is_correct": False, "attempts": 1, "submit_time": "2025-01-02T00:00:00Z"},
                {"log_id": "e3", "user_id": "u", "problem_id": "p-missing", "is_correct": True, "submit_time": "2025-01-03T00:00:00Z"},
                {"log_id": "e4", "user_id": "u", "problem_id": "p-missing", "is_correct": True, "submit_time": "2025-02-30 00:00:00"},
            ]), encoding="utf-8")
            output, staging = root / "processed", root / "staging"
            first = _clean_payload(raw, output, staging, "cs", 42, 5, .5, .25)
            self.assertEqual((output / "concepts.csv").read_bytes()[:3], b"\xef\xbb\xbf")
            with (output / "concepts.csv").open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(next(csv.DictReader(stream))["name"], "外部中断")
            second = _clean_payload(raw, output, staging, "cs", 42, 5, .5, .25)
            with (output / "interactions_clean.csv").open(encoding="utf-8", newline="") as stream:
                interactions = list(csv.DictReader(stream))
            with (output / "learner_state.csv").open(encoding="utf-8", newline="") as stream:
                state = list(csv.DictReader(stream))
            with gzip.open(output / "records_unmatched.csv.gz", "rt", encoding="utf-8", newline="") as stream:
                unmatched = list(csv.DictReader(stream))
            self.assertEqual(first["duplicate_stored_rows"], 1)
            self.assertEqual(first["interactions_invalid"], 1)
            self.assertEqual(first["interactions_unmatched_any_concept"], 1)
            self.assertEqual(second["interactions_clean"], 2)
            self.assertEqual(len(interactions), 2)
            self.assertEqual(len(state), 2)
            self.assertEqual({row["total_count"] for row in state}, {"1"})
            self.assertEqual(unmatched[0]["problem_id"], "p-missing")


if __name__ == "__main__":
    unittest.main()
