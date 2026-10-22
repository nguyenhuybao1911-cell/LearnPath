"""Verify generated CSV relationships, chronological splits, and compressed unmatched log."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from pathlib import Path


def rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream)


def count_gzip_csv_data_lines(path: Path, chunk_size: int = 4 * 1024 * 1024) -> int:
    """Count flat CSV records quickly while reading gzip through EOF (CRC check)."""
    with gzip.open(path, "rb") as stream:
        header = stream.readline()
        if not header:
            return 0
        count = 0
        last_byte = b""
        while chunk := stream.read(chunk_size):
            count += chunk.count(b"\n")
            last_byte = chunk[-1:]
        if last_byte and last_byte != b"\n":
            count += 1
        return count


def verify(output: Path, profile_path: Path, allow_unmatched_removed: bool = False) -> dict:
    summary = json.loads((output / "data_summary.json").read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    domain = summary["domain"]
    profile_domain = profile["domains"][domain]

    counts = {}
    for filename in ("concepts.csv", "problems.csv", "problem_concepts.csv", "prerequisites.csv",
                     "interactions_clean.csv", "learners.csv", "learner_state.csv", "concept_difficulty.csv"):
        counts[filename] = sum(1 for _ in rows(output / filename))
    assert counts["concepts.csv"] == summary["concepts"]
    assert counts["problems.csv"] == summary["problems"]
    assert counts["prerequisites.csv"] == summary["prerequisite_rows"]
    assert counts["interactions_clean.csv"] == summary["interactions_clean"]
    assert counts["learners.csv"] == summary["selected_learners"]
    assert counts["learner_state.csv"] == summary["learner_state_rows_at_test_start"]
    assert counts["concepts.csv"] == profile_domain["candidate_concepts"]
    assert counts["interactions_clean.csv"] == profile_domain["interactions"]
    assert summary["split_counts"] == profile_domain["temporal_split_counts"]

    concepts = {row["id"] for row in rows(output / "concepts.csv")}
    problems = {row["id"] for row in rows(output / "problems.csv")}
    learners = {row["id"] for row in rows(output / "learners.csv")}
    problem_concepts = {}
    link_pairs = set()
    for row in rows(output / "problem_concepts.csv"):
        assert row["problem_id"] in problems
        assert row["concept_id"] in concepts
        link_pairs.add((row["problem_id"], row["concept_id"]))
        problem_concepts.setdefault(row["problem_id"], set()).add(row["concept_id"])
    assert len(link_pairs) == counts["problem_concepts.csv"]

    split_counts = {"train": 0, "validation": 0, "test": 0}
    seen_logs = set()
    for row in rows(output / "interactions_clean.csv"):
        assert row["learner_id"] in learners and row["problem_id"] in problems
        assert row["log_id"] not in seen_logs
        seen_logs.add(row["log_id"])
        assert row["is_correct"] in ("True", "False")
        assert problem_concepts[row["problem_id"]]
        split_counts[row["dataset_split"]] += 1
    assert split_counts == summary["split_counts"]

    for row in rows(output / "learner_state.csv"):
        total, correct = int(row["total_count"]), int(row["correct_count"])
        assert row["learner_id"] in learners and row["concept_id"] in concepts
        assert total > 0 and 0 <= correct <= total
        assert abs(float(row["mastery"]) - correct / total) < 1e-12
        assert row["as_of"] == summary["state_as_of"]
    assert all(row["derived_from_split"] == "train" for row in rows(output / "concept_difficulty.csv"))

    for row in rows(output / "prerequisites.csv"):
        assert row["prerequisite_id"] in concepts and row["concept_id"] in concepts
        if row["ground_truth"] == "1":
            assert row["annotated"] == "True"
    unmatched_path = output / "records_unmatched.csv.gz"
    if unmatched_path.is_file():
        unmatched_count = count_gzip_csv_data_lines(unmatched_path)
        assert unmatched_count == summary["interactions_unmatched_any_concept"]
    else:
        assert allow_unmatched_removed, "records_unmatched.csv.gz is missing"
        unmatched_count = None

    return {
        "domain": domain,
        "file_rows": counts,
        "split_counts": split_counts,
        "unique_interaction_log_ids": len(seen_logs),
        "unmatched_csv_gzip_rows_crc_checked": unmatched_count,
        "unmatched_file_removed_after_prior_verification": unmatched_count is None,
        "profile_and_pipeline_counts_match": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=Path("data/processed/domain_coverage_profile.json"))
    parser.add_argument("--allow-unmatched-removed", action="store_true",
                        help="Verify retained outputs after the optional unmatched audit file was removed")
    args = parser.parse_args()
    print(json.dumps(verify(args.data, args.profile, args.allow_unmatched_removed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
