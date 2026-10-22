"""Compare exact learner-history coverage for MOOCCubeX prerequisite domains."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from src.ingest import _correct, _timestamp, iter_json_records
from src.pipeline import DOMAIN_FIELDS, parse_prerequisites, resolve_domain_concepts


def profile_interactions(records: Iterable[dict], domain_problem_concepts: dict[str, dict[str, set[str]]],
                         minimum: int = 2000, connection: sqlite3.Connection | None = None,
                         train_ratio: float = .70, validation_ratio: float = .15) -> dict[str, dict]:
    """Count distinct valid source events that exactly join to each domain."""
    if minimum < 1:
        raise ValueError("minimum must be positive")
    if not 0 < train_ratio < 1 or not 0 < validation_ratio < 1 or train_ratio + validation_ratio >= 1:
        raise ValueError("train and validation ratios must be positive and sum to less than 1")
    own_connection = connection is None
    connection = connection or sqlite3.connect(":memory:")
    connection.executescript("""
        drop table if exists coverage_event;
        drop table if exists coverage_concept;
        create table coverage_event(
            domain text not null, log_id text not null, learner_id text not null,
            problem_id text not null, is_correct integer not null, submitted_at text not null,
            primary key(domain, log_id)
        ) without rowid;
        create table coverage_concept(
            domain text not null, log_id text not null, concept_id text not null,
            primary key(domain, log_id, concept_id)
        ) without rowid;
    """)
    duplicate_ids = defaultdict(int)
    conflicting_ids = defaultdict(int)
    invalid_linked = defaultdict(int)
    pending = 0

    for raw in records:
        problem_id = raw.get("problem_id")
        matches = {domain: links[problem_id] for domain, links in domain_problem_concepts.items()
                   if isinstance(problem_id, str) and problem_id in links}
        if not matches:
            continue
        try:
            log_id, learner_id = raw.get("log_id"), raw.get("user_id")
            if not isinstance(log_id, str) or not log_id.strip():
                raise ValueError("missing_log_id")
            if not isinstance(learner_id, str) or not learner_id.strip():
                raise ValueError("missing_user_id")
            correct = _correct(raw.get("is_correct"))
            submitted_at = _timestamp(raw.get("submit_time"))
        except (ValueError, OverflowError, OSError):
            for domain in matches:
                invalid_linked[domain] += 1
            continue

        for domain, concepts in matches.items():
            current = (learner_id, problem_id, int(correct), submitted_at)
            previous = connection.execute(
                "select learner_id,problem_id,is_correct,submitted_at from coverage_event where domain=? and log_id=?",
                (domain, log_id)).fetchone()
            if previous is not None:
                duplicate_ids[domain] += 1
                if previous != current:
                    conflicting_ids[domain] += 1
                continue
            connection.execute("insert into coverage_event values(?,?,?,?,?,?)", (domain, log_id, *current))
            connection.executemany("insert into coverage_concept values(?,?,?)",
                                   ((domain, log_id, concept_id) for concept_id in concepts))
            pending += 1
            if pending % 10000 == 0:
                connection.commit()

    profiles = {}
    connection.commit()
    for domain in domain_problem_concepts:
        interactions, learners, problems, first, last = connection.execute(
            "select count(*),count(distinct learner_id),count(distinct problem_id),min(submitted_at),max(submitted_at) "
            "from coverage_event where domain=?", (domain,)).fetchone()
        concepts = connection.execute("select count(distinct concept_id) from coverage_concept where domain=?",
                                      (domain,)).fetchone()[0]
        links = connection.execute("select count(*) from coverage_concept where domain=?", (domain,)).fetchone()[0]
        multi = connection.execute("select count(*) from (select log_id from coverage_concept where domain=? "
                                    "group by log_id having count(*)>1)", (domain,)).fetchone()[0]
        train_index = int(interactions * train_ratio)
        validation_index = int(interactions * (train_ratio + validation_ratio))
        train_row = connection.execute(
            "select submitted_at from coverage_event where domain=? order by submitted_at,log_id limit 1 offset ?",
            (domain, train_index)).fetchone()
        validation_row = connection.execute(
            "select submitted_at from coverage_event where domain=? order by submitted_at,log_id limit 1 offset ?",
            (domain, validation_index)).fetchone()
        train_cutoff = train_row[0] if train_row else None
        validation_cutoff = validation_row[0] if validation_row else None
        if train_cutoff and validation_cutoff:
            split_counts = connection.execute(
                "select sum(submitted_at<?),sum(submitted_at>=? and submitted_at<?),sum(submitted_at>=?) "
                "from coverage_event where domain=?",
                (train_cutoff, train_cutoff, validation_cutoff, validation_cutoff, domain)).fetchone()
            train_count, validation_count, test_count = (value or 0 for value in split_counts)
            learners_at_cutoff = connection.execute(
                "select count(distinct learner_id) from coverage_event where domain=? and submitted_at<?",
                (domain, validation_cutoff)).fetchone()[0]
            learners_with_two_train_events = connection.execute(
                "select count(*) from (select learner_id from coverage_event where domain=? and submitted_at<? "
                "group by learner_id having count(*)>=2)", (domain, train_cutoff)).fetchone()[0]
            max_train_events_per_learner = connection.execute(
                "select coalesce(max(n),0) from (select count(*) n from coverage_event where domain=? and submitted_at<? "
                "group by learner_id)", (domain, train_cutoff)).fetchone()[0]
            train_concepts = connection.execute(
                "select count(distinct c.concept_id) from coverage_concept c join coverage_event e "
                "on e.domain=c.domain and e.log_id=c.log_id where c.domain=? and e.submitted_at<?",
                (domain, train_cutoff)).fetchone()[0]
            train_correct = connection.execute(
                "select coalesce(sum(is_correct),0) from coverage_event where domain=? and submitted_at<?",
                (domain, train_cutoff)).fetchone()[0]
        else:
            train_count = validation_count = 0
            test_count = interactions
            learners_at_cutoff = learners_with_two_train_events = max_train_events_per_learner = 0
            train_concepts = train_correct = 0
        profiles[domain] = {
            "interactions": interactions,
            "temporal_split_counts": {"train": train_count, "validation": validation_count, "test": test_count},
            "learners_with_history_at_test_start": learners_at_cutoff,
            "learners_with_at_least_two_train_events": learners_with_two_train_events,
            "max_train_events_for_one_learner": max_train_events_per_learner,
            "train_concepts_with_history": train_concepts,
            "train_correct_rate": train_correct / train_count if train_count else None,
            "train_cutoff_utc": train_cutoff,
            "validation_cutoff_utc": validation_cutoff,
            "state_as_of_utc": validation_cutoff,
            "learners": learners,
            "problems_with_history": problems,
            "concepts_with_history": concepts,
            "interaction_concept_links": links,
            "multi_concept_interactions": multi,
            "duplicate_log_ids": duplicate_ids[domain],
            "conflicting_duplicate_log_ids": conflicting_ids[domain],
            "invalid_linked_records": invalid_linked[domain],
            "meets_minimum_train_interactions": train_count >= minimum,
            "linked_event_first_utc": first,
            "linked_event_last_utc": last,
        }
    if own_connection:
        connection.close()
    return profiles


def _domain_resources(raw: Path, domain: str) -> tuple[set[str], dict[str, set[str]], int, int, int, int]:
    prereq_path = raw / "prerequisites" / f"{domain}.json"
    concepts_path = raw / "entities" / "concept.json"
    relation_path = raw / "relations" / "concept-problem.txt"
    domain_names = {row[field] for row in iter_json_records(prereq_path)
                    for field in ("c1", "c2") if isinstance(row.get(field), str)}
    resolution = resolve_domain_concepts(iter_json_records(concepts_path), domain_names, domain)
    endpoint_concept_ids = set(resolution.name_to_id.values())
    concept_ids = endpoint_concept_ids | resolution.field_concept_ids

    def resolved_prerequisites():
        for row in iter_json_records(prereq_path):
            parent, child = resolution.name_to_id.get(row.get("c1")), resolution.name_to_id.get(row.get("c2"))
            if parent is not None and child is not None:
                yield {**row, "c1": parent, "c2": child}

    prerequisite_result = parse_prerequisites(resolved_prerequisites(), concept_ids,
                                               f"MOOCCubeX:prerequisites/{domain}.json")
    problem_concepts: dict[str, set[str]] = defaultdict(set)
    links = set()
    with relation_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) != 2:
                continue
            concept_id, problem_id = parts
            if concept_id in concept_ids:
                links.add((problem_id, concept_id))
                problem_concepts[problem_id].add(concept_id)
    return concept_ids, problem_concepts, len(links), len(prerequisite_result.edges), len(endpoint_concept_ids), len(resolution.field_concept_ids)


def profile_payload(raw: Path, minimum: int = 2000, staging: Path | None = None,
                    train_ratio: float = .70, validation_ratio: float = .15) -> dict:
    required = [raw / "entities" / "concept.json", raw / "relations" / "concept-problem.txt",
                raw / "relations" / "user-problem.json"]
    required.extend(raw / "prerequisites" / f"{domain}.json" for domain in DOMAIN_FIELDS)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing official MOOCCubeX files: " + ", ".join(missing))

    maps = {}
    metadata = {}
    for domain in DOMAIN_FIELDS:
        concept_ids, problem_concepts, problem_link_rows, prerequisite_edges, endpoint_concepts, field_concepts = _domain_resources(raw, domain)
        maps[domain] = problem_concepts
        metadata[domain] = {"concepts_with_prerequisite_endpoints": endpoint_concepts,
                            "concepts_with_exact_domain_field": field_concepts,
                            "concepts_resolved_from_prerequisite_endpoints": endpoint_concepts,
                            "candidate_concepts": len(concept_ids),
                            "problem_concept_links": problem_link_rows,
                            "annotated_prerequisite_edges": prerequisite_edges}
    staging = staging or raw.parent / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="coverage-", dir=staging) as temporary:
        connection = sqlite3.connect(Path(temporary) / "coverage.sqlite3")
        profiles = profile_interactions(iter_json_records(required[2]), maps, minimum, connection,
                                        train_ratio, validation_ratio)
        connection.close()
    candidates = [domain for domain in DOMAIN_FIELDS if metadata[domain]["annotated_prerequisite_edges"] > 0]
    recommended = max(candidates, key=lambda domain: (profiles[domain]["temporal_split_counts"]["train"],
                                                       metadata[domain]["annotated_prerequisite_edges"], domain)) if candidates else None
    return {
        "source": "MOOCCubeX",
        "minimum_train_interactions_from_advisor": minimum,
        "temporal_split_ratios": {"train": train_ratio, "validation": validation_ratio,
                                  "test": 1 - train_ratio - validation_ratio},
        "exact_id_join_only": True,
        "domains": {domain: {**metadata[domain], **profiles[domain]} for domain in DOMAIN_FIELDS},
        "best_supported_domain": recommended,
        "best_supported_domain_meets_minimum_train_interactions": bool(
            recommended and profiles[recommended]["meets_minimum_train_interactions"]),
        "minimum_is_a_screening_requirement_not_evidence_of_model_generalization": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/mooccubex"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/domain_coverage_profile.json"))
    parser.add_argument("--staging", type=Path, default=Path("data/staging"))
    parser.add_argument("--minimum-train-interactions", "--minimum-interactions",
                        dest="minimum_train_interactions", type=int, default=2000)
    parser.add_argument("--train-ratio", type=float, default=.70)
    parser.add_argument("--validation-ratio", type=float, default=.15)
    args = parser.parse_args()
    report = profile_payload(args.raw, args.minimum_train_interactions, args.staging,
                             args.train_ratio, args.validation_ratio)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"best_supported_domain": report["best_supported_domain"],
                      "best_supported_domain_meets_minimum_train_interactions":
                          report["best_supported_domain_meets_minimum_train_interactions"],
                      "domains": {domain: {key: value[key] for key in
                                            ("interactions", "learners", "problems_with_history",
                                             "concepts_with_history", "annotated_prerequisite_edges",
                                             "temporal_split_counts", "learners_with_history_at_test_start",
                                             "learners_with_at_least_two_train_events",
                                             "train_concepts_with_history", "train_correct_rate",
                                             "meets_minimum_train_interactions")}
                                  for domain, value in report["domains"].items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
