import json
import tempfile
import unittest
from pathlib import Path

from src.ingest import clean_interactions, is_valid_timestamp, iter_json_records


class IngestTests(unittest.TestCase):
    def test_fast_timestamp_validation_checks_calendar_without_normalizing(self):
        self.assertTrue(is_valid_timestamp("2020-02-29 10:11:12"))
        self.assertFalse(is_valid_timestamp("2021-02-29 10:11:12"))
        self.assertFalse(is_valid_timestamp("2020-13-01 10:11:12"))
        self.assertTrue(is_valid_timestamp(1767225600))

    def test_reads_json_array_incrementally(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.json"
            path.write_text(json.dumps([{"id": 1}, {"id": 2}]), encoding="utf-8")
            self.assertEqual(list(iter_json_records(path, chunk_size=5)), [{"id": 1}, {"id": 2}])

    def test_duplicate_storage_is_removed_but_distinct_attempt_logs_remain(self):
        records = [
            {"log_id": "l1", "user_id": "u", "problem_id": "p", "is_correct": True, "submit_time": "2025-01-01T00:00:00Z"},
            {"log_id": "l1", "user_id": "u", "problem_id": "p", "is_correct": True, "submit_time": "2025-01-01T00:00:00Z"},
            {"log_id": "l2", "user_id": "u", "problem_id": "p", "is_correct": False, "submit_time": "2025-01-02T00:00:00Z"},
        ]
        result = clean_interactions(records, {"p": {"c1", "c2"}})
        self.assertEqual([row.log_id for row in result.clean], ["l1", "l2"])
        self.assertEqual(result.duplicate_rows, 1)
        self.assertEqual(result.clean[0].concept_ids, {"c1", "c2"})
        self.assertEqual(result.clean[0].timestamp, "2025-01-01T00:00:00.000000+00:00")

    def test_invalid_rows_and_unmatched_problem_are_recorded(self):
        records = [
            {"log_id": "bad", "user_id": "u", "problem_id": "p", "is_correct": 3, "submit_time": "nope"},
            {"log_id": "ok", "user_id": "u", "problem_id": "missing", "is_correct": 0, "submit_time": 1767225600},
        ]
        result = clean_interactions(records, {})
        self.assertEqual(result.rejected[0]["reason"], "invalid_correctness")
        self.assertEqual(result.unmatched_rows, 1)
        self.assertEqual(result.clean[0].timestamp, "2026-01-01T00:00:00.000000+00:00")


if __name__ == "__main__":
    unittest.main()
