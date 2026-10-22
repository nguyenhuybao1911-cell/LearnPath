import unittest
from datetime import datetime, timezone

from src.planner import Concept, Edge, Interaction, Mastery, Weights, learner_state_at, recommend


class PlannerTests(unittest.TestCase):
    def test_state_uses_only_interactions_before_cutoff_and_keeps_retries(self):
        interactions = [
            Interaction("l1", "p1", True, datetime(2025, 1, 1, tzinfo=timezone.utc), "a"),
            Interaction("l1", "p1", False, datetime(2025, 1, 1, tzinfo=timezone.utc), "b"),
            Interaction("l1", "p2", True, datetime(2025, 2, 1, tzinfo=timezone.utc), "c"),
        ]
        state = learner_state_at(interactions, {"p1": {"c1"}, "p2": {"c2"}}, "l1", datetime(2025, 1, 15, tzinfo=timezone.utc))
        self.assertEqual(state["c1"].correct, 1)
        self.assertEqual(state["c1"].total, 2)
        self.assertNotIn("c2", state)

    def test_unknown_mastery_is_not_treated_as_mastered_and_target_can_be_known(self):
        concepts = {"a": Concept("a", "A"), "b": Concept("b", "B")}
        as_of = datetime(2025, 2, 1, tzinfo=timezone.utc)
        result = recommend("learner", "a", concepts, [], {"a": Mastery(2, 2, as_of)}, {}, tau=0.7, min_interactions=2)
        self.assertEqual(result.status, "target_already_mastered")
        result = recommend("learner", "b", concepts, [], {}, {}, tau=0.7, min_interactions=2)
        self.assertEqual(result.status, "reached")
        self.assertEqual([x.concept_id for x in result.steps], ["b"])

    def test_candidate_requires_all_prerequisites_and_open_keeps_alternative_branches(self):
        concepts = {key: Concept(key, key.upper()) for key in "abct"}
        edges = [Edge("a", "t"), Edge("b", "t"), Edge("c", "a")]
        result = recommend("l", "t", concepts, edges, {}, {k: 0.5 for k in concepts}, max_states=50)
        self.assertEqual(result.status, "reached")
        self.assertGreater(result.peak_open, 1)
        self.assertGreaterEqual(result.expanded, 2)
        self.assertEqual(result.steps[-1].concept_id, "t")

    def test_search_reports_unreachable_and_budget_exhaustion(self):
        concepts = {key: Concept(key, key) for key in "abt"}
        disconnected = recommend("l", "t", concepts, [Edge("a", "t"), Edge("b", "t")], {}, {}, max_states=50, allowed_concepts={"a", "t"})
        self.assertEqual(disconnected.status, "no_path")
        limited = recommend("l", "t", concepts, [Edge("a", "t"), Edge("b", "t")], {}, {}, max_states=1)
        self.assertEqual(limited.status, "budget_exhausted")

    def test_graph_rejects_unknown_nodes_self_loops_and_cycles(self):
        concepts = {"a": Concept("a", "A"), "b": Concept("b", "B")}
        with self.assertRaises(ValueError):
            recommend("l", "b", concepts, [Edge("a", "missing")], {}, {})
        with self.assertRaises(ValueError):
            recommend("l", "b", concepts, [Edge("a", "a")], {}, {})
        with self.assertRaises(ValueError):
            recommend("l", "b", concepts, [Edge("a", "b"), Edge("b", "a")], {}, {})

    def test_weights_must_be_nonnegative_and_sum_to_one(self):
        with self.assertRaises(ValueError):
            Weights(0.0, 0.4, 0.4, 0.3)
        with self.assertRaises(ValueError):
            Weights(-0.1, 0.4, 0.4, 0.3)


if __name__ == "__main__":
    unittest.main()
