import math
import sqlite3
import tempfile
import unittest
from pathlib import Path

from datetime import datetime, timezone

from src.experiment import _learner_sample, _read_csv, eligible_plan, mastered_at_threshold, ranking_metrics
from src.planner import Concept, Edge, Mastery


class ExperimentTests(unittest.TestCase):
    def test_csv_reader_accepts_excel_friendly_utf8_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "concepts.csv"
            path.write_text("\ufeffid,name\nc1,外部中断\n", encoding="utf-8")
            self.assertEqual(_read_csv(path), [{"id": "c1", "name": "外部中断"}])

    def test_ranking_metrics_use_shorter_returned_route_as_precision_denominator(self):
        result = ranking_metrics(["a", "b"], {"a", "c"}, 5)
        self.assertEqual(result["precision"], 0.5)
        self.assertEqual(result["recall"], 0.5)
        self.assertAlmostEqual(result["ndcg"], 1 / (1 + 1 / math.log2(3)))

    def test_empty_future_is_undefined_and_fixed_order_obeys_prerequisites(self):
        self.assertIsNone(ranking_metrics(["a"], set(), 5)["ndcg"])
        concepts = {cid: Concept(cid, cid) for cid in "abt"}
        result = eligible_plan("t", concepts, [Edge("a", "t"), Edge("b", "t")], set(), strategy="fixed")
        self.assertEqual(result[:2], ["a", "b"])
        self.assertEqual(result[-1], "t")

    def test_all_methods_can_share_validation_selected_mastery_threshold(self):
        now = datetime.now(timezone.utc)
        state = {"enough": Mastery(2, 2, now), "low": Mastery(1, 2, now), "few": Mastery(1, 1, now)}
        self.assertEqual(mastered_at_threshold(state, .7, 2), {"enough"})

    def test_evaluation_sample_does_not_select_learners_from_future_events(self):
        connection = sqlite3.connect(":memory:")
        connection.execute("create table interaction(learner_id text, submitted_at text)")
        connection.executemany("insert into interaction values(?,?)", [
            ("past", "2025-01-01T00:00:00.000000+00:00"),
            ("future-only", "2025-02-01T00:00:00.000000+00:00"),
        ])
        self.assertEqual(_learner_sample(connection, 10, 42, "2025-01-15T00:00:00.000000+00:00"), ["past"])
        connection.close()


if __name__ == "__main__":
    unittest.main()
