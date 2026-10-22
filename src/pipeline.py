"""Stream MOOCCubeX into a deterministic, Computer Science concept dataset."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import heapq
import json
import math
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .ingest import CleanInteraction, _correct, clean_interactions, is_valid_timestamp, iter_json_records


@dataclass
class PrerequisiteData:
    rows: list[dict]
    edges: list
    rejected: list[dict]


@dataclass
class ConceptResolution:
    name_to_id: dict[str, str]
    rejected: list[dict]
    field_concept_ids: set[str]


DOMAIN_FIELDS = {
    "cs": "计算机科学与技术",
    "math": "数学",
    "psy": "心理学",
}


def resolve_domain_concepts(records: Iterable[dict], endpoint_names: set[str], domain: str) -> ConceptResolution:
    """Resolve prerequisite names and catalog concepts using exact field metadata/ID suffixes."""
    candidates: dict[str, list[tuple[str, str | None]]] = {name: [] for name in endpoint_names}
    direct_ids: dict[str, str] = {}
    field_concept_ids: set[str] = set()
    expected_field = DOMAIN_FIELDS[domain]
    for row in records:
        cid, name = row.get("id"), row.get("name")
        if not isinstance(cid, str) or not cid:
            continue
        if row.get("field") == expected_field or cid.endswith("_" + expected_field):
            field_concept_ids.add(cid)
        if cid in endpoint_names:
            direct_ids[cid] = cid
        if isinstance(name, str) and name in candidates:
            field = row.get("field")
            if not isinstance(field, str):
                field = None
            candidates[name].append((cid, field))

    result = dict(direct_ids)
    rejected: list[dict] = []
    for name in sorted(endpoint_names - direct_ids.keys()):
        options = candidates[name]
        preferred = [cid for cid, field in options
                     if field == expected_field or cid.endswith("_" + expected_field)]
        if len(preferred) == 1:
            result[name] = preferred[0]
            continue
        if len(preferred) > 1:
            reason = "ambiguous_concept_name"
        elif len(options) == 1 and options[0][0].endswith("_not-field"):
            # MOOCCubeX prerequisite files already scope these records by domain;
            # the catalog uses this suffix when a concept has no field annotation.
            result[name] = options[0][0]
            continue
        elif not options:
            reason = "unknown_concept_name"
        elif len(options) == 1:
            reason = "concept_field_mismatch"
        else:
            reason = "ambiguous_concept_name"
        rejected.append({
            "record_id": name,
            "reason": reason,
            "details": " | ".join(cid for cid, _ in options),
        })
    return ConceptResolution(result, rejected, field_concept_ids)


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _probability(value: object) -> float | None:
    if isinstance(value, (list, tuple)):
        if len(value) != 2:
            return None
        value = value[1]
    result = _number(value)
    return result if result is not None and 0 <= result <= 1 else None


def _label(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if value in (0, "0"):
        return 0
    if value in (1, "1"):
        return 1
    return None


def _path_exists(start: str, target: str, graph: dict[str, set[str]]) -> bool:
    pending = [start]
    seen = set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current not in seen:
            seen.add(current)
            pending.extend(graph.get(current, ()))
    return False


def parse_prerequisites(records: Iterable[dict], known_concepts: set[str], source: str = "MOOCCubeX:prerequisites") -> PrerequisiteData:
    """Keep annotation labels and model scores separate; omit broken graph edges with reasons."""
    from .planner import Edge

    rows: list[dict] = []
    edges: list[Edge] = []
    rejected: list[dict] = []
    graph: dict[str, set[str]] = {}
    pairs: set[tuple[str, str]] = set()
    for row in records:
        parent, child = row.get("c1"), row.get("c2")
        if not isinstance(parent, str) or not parent or not isinstance(child, str) or not child:
            rejected.append({"record_id": "", "reason": "missing_concept_id", "details": "c1/c2"})
            continue
        if parent not in known_concepts or child not in known_concepts:
            rejected.append({"record_id": f"{parent}->{child}", "reason": "unknown_concept_id", "details": "ID not found in entities/concept.json"})
            continue
        pair = parent, child
        if pair in pairs:
            rejected.append({"record_id": f"{parent}->{child}", "reason": "duplicate_prerequisite", "details": "duplicate c1/c2 pair"})
            continue
        truth = _label(row.get("ground_truth"))
        if row.get("ground_truth") not in (None, "", -1, "-1") and truth is None:
            rejected.append({"record_id": f"{parent}->{child}", "reason": "invalid_ground_truth", "details": str(row.get("ground_truth"))})
            continue
        if parent == child and truth == 1:
            rejected.append({"record_id": f"{parent}->{child}", "reason": "self_loop", "details": "annotated prerequisite"})
            continue
        if truth == 1 and _path_exists(child, parent, graph):
            rejected.append({"record_id": f"{parent}->{child}", "reason": "would_create_cycle", "details": "annotated edge excluded from search graph"})
            continue
        pairs.add(pair)
        if truth == 1:
            graph.setdefault(parent, set()).add(child)
            edges.append(Edge(parent, child))
        rows.append({
            "prerequisite_id": parent,
            "concept_id": child,
            "source": source,
            "ground_truth": truth,
            "text_predict": _probability(row.get("text_predict")),
            "graph_predict": _probability(row.get("graph_predict")),
            "annotated": truth is not None,
        })
    return PrerequisiteData(rows, edges, rejected)


def split_for_index(index: int, count: int, train_ratio: float, validation_ratio: float) -> str:
    if count < 0 or not 0 < train_ratio < 1 or not 0 < validation_ratio < 1 or train_ratio + validation_ratio >= 1:
        raise ValueError("split ratios must be positive and sum to less than 1")
    if index < int(count * train_ratio):
        return "train"
    if index < int(count * (train_ratio + validation_ratio)):
        return "validation"
    return "test"


def split_for_timestamp(timestamp: str, train_cutoff: str, validation_cutoff: str) -> str:
    """Use strict cutoffs so events sharing a timestamp cannot leak across splits."""
    if timestamp < train_cutoff:
        return "train"
    if timestamp < validation_cutoff:
        return "validation"
    return "test"


def _write_csv(path: Path, header: list[str]):
    stream = path.open("w", newline="", encoding="utf-8-sig")
    writer = csv.writer(stream)
    writer.writerow(header)
    return stream, writer


def _selected_learners(connection: sqlite3.Connection, limit: int | None, seed: int) -> set[str] | None:
    if limit is None:
        return None
    if limit < 1:
        raise ValueError("max_learners must be positive")
    keep: list[tuple[int, str]] = []
    for (learner_id,) in connection.execute("select id from learners"):
        rank = int.from_bytes(hashlib.sha256(f"{seed}:{learner_id}".encode()).digest()[:8], "big")
        entry = (-rank, learner_id)
        if len(keep) < limit:
            heapq.heappush(keep, entry)
        elif entry > keep[0]:
            heapq.heapreplace(keep, entry)
    return {learner for _, learner in keep}


def _clean_payload(raw: Path, output: Path, staging: Path, domain: str, seed: int,
                   max_learners: int | None, train_ratio: float, validation_ratio: float) -> dict:
    required = {
        "concepts": raw / "entities" / "concept.json",
        "links": raw / "relations" / "concept-problem.txt",
        "interactions": raw / "relations" / "user-problem.json",
        "prerequisites": raw / "prerequisites" / f"{domain}.json",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing official MOOCCubeX payloads: " + ", ".join(missing))
    for ratio in (train_ratio, validation_ratio):
        if not 0 < ratio < 1:
            raise ValueError("split ratios must be between 0 and 1")
    if train_ratio + validation_ratio >= 1:
        raise ValueError("train and validation ratios must sum to less than 1")

    output.mkdir(parents=True, exist_ok=True)
    staging.mkdir(parents=True, exist_ok=True)
    issue_stream, issues = _write_csv(output / "records_rejected.csv", ["record_type", "record_id", "reason", "details"])
    unmatched_stream = gzip.open(output / "records_unmatched.csv.gz", "wt", newline="", encoding="utf-8", compresslevel=1)
    unmatched = csv.writer(unmatched_stream)
    unmatched.writerow(["log_id", "learner_id", "problem_id", "reason"])
    try:
        domain_names: set[str] = set()
        for row in iter_json_records(required["prerequisites"]):
            for field in ("c1", "c2"):
                if isinstance(row.get(field), str):
                    domain_names.add(row[field])

        resolution = resolve_domain_concepts(iter_json_records(required["concepts"]), domain_names, domain)
        for issue in resolution.rejected:
            issues.writerow(["prerequisite_concept", issue["record_id"], issue["reason"], issue["details"]])
        domain_concept_ids = set(resolution.name_to_id.values()) | resolution.field_concept_ids

        concept_ids: set[str] = set()
        concept_names: dict[str, str] = {}
        concept_file = output / "concepts.csv"
        concepts_stream, concepts_writer = _write_csv(concept_file, ["id", "name", "field"])
        for row in iter_json_records(required["concepts"]):
            cid = row.get("id")
            if not isinstance(cid, str) or not cid:
                issues.writerow(["concept", "", "missing_id", "entities/concept.json"])
                continue
            concept_ids.add(cid)
            if cid in domain_concept_ids:
                name = row.get("name")
                if not isinstance(name, str) or not name.strip():
                    issues.writerow(["concept", cid, "missing_name", "not included in concepts.csv"])
                else:
                    concept_names[cid] = name
                    concepts_writer.writerow([cid, name, domain])
        concepts_stream.close()
        if not concept_names:
            raise ValueError(f"No {domain} concepts joined to entities/concept.json")

        skipped_unresolved_prerequisites = 0
        def mapped_prerequisites():
            nonlocal skipped_unresolved_prerequisites
            for row in iter_json_records(required["prerequisites"]):
                parent = resolution.name_to_id.get(row.get("c1"))
                child = resolution.name_to_id.get(row.get("c2"))
                if parent is None or child is None:
                    skipped_unresolved_prerequisites += 1
                    continue
                yield {**row, "c1": parent, "c2": child}

        prerequisite_result = parse_prerequisites(mapped_prerequisites(), set(concept_names), f"MOOCCubeX:prerequisites/{domain}.json")
        for issue in prerequisite_result.rejected:
            issues.writerow(["prerequisite", issue["record_id"], issue["reason"], issue["details"]])
        prereq_stream, prereq_writer = _write_csv(output / "prerequisites.csv",
                ["prerequisite_id", "concept_id", "source", "ground_truth", "text_predict", "graph_predict", "annotated"])
        for row in prerequisite_result.rows:
            prereq_writer.writerow([row[key] if row[key] is not None else "" for key in
                                    ("prerequisite_id", "concept_id", "source", "ground_truth", "text_predict", "graph_predict", "annotated")])
        prereq_stream.close()

        problem_concepts: dict[str, set[str]] = {}
        relation_seen: set[tuple[str, str]] = set()
        relation_rows = relation_duplicates = domain_link_rows = 0
        links_stream, links_writer = _write_csv(output / "problem_concepts.csv", ["problem_id", "concept_id"])
        with required["links"].open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) != 2 or not all(parts):
                    issues.writerow(["problem_concept", str(line_number), "invalid_relation", "expected Concept ID<TAB>Question ID"])
                    continue
                cid, pid = parts
                relation_rows += 1
                if cid not in concept_ids:
                    issues.writerow(["problem_concept", f"{cid}->{pid}", "unknown_concept_id", "not found in entities/concept.json"])
                    continue
                pair = cid, pid
                if pair in relation_seen:
                    relation_duplicates += 1
                    continue
                relation_seen.add(pair)
                problem_concepts.setdefault(pid, set()).add(cid)
                if cid in concept_names:
                    links_writer.writerow([pid, cid])
                    domain_link_rows += 1
        links_stream.close()

        all_links = problem_concepts
        domain_links = {pid: concepts & set(concept_names) for pid, concepts in all_links.items() if concepts & set(concept_names)}
        problem_stream, problem_writer = _write_csv(output / "problems.csv", ["id", "title"])
        for pid in sorted(domain_links):
            problem_writer.writerow([pid, ""])
        problem_stream.close()

        matched = unmatched_count = outside_domain = invalid = duplicate_rows = in_scope = domain_matched = multi_concept_rows = 0
        db_path_dir = staging
        with tempfile.TemporaryDirectory(prefix="learnpath-", dir=db_path_dir) as tmp:
            conn = sqlite3.connect(Path(tmp) / "stage.sqlite3")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE learners(id TEXT PRIMARY KEY);
                CREATE TABLE interaction(
                    log_id TEXT PRIMARY KEY, learner_id TEXT NOT NULL, problem_id TEXT NOT NULL,
                    is_correct INTEGER NOT NULL, score REAL, source_attempts INTEGER, submitted_at TEXT NOT NULL,
                    concept_ids TEXT NOT NULL
                );
                CREATE INDEX interaction_time_idx ON interaction(submitted_at, log_id);
                CREATE TABLE learner_state(
                    learner_id TEXT NOT NULL, concept_id TEXT NOT NULL,
                    correct_count INTEGER NOT NULL, total_count INTEGER NOT NULL,
                    PRIMARY KEY(learner_id, concept_id)
                );
            """)
            raw_rows = 0
            with conn:
                for raw_row in iter_json_records(required["interactions"]):
                    raw_rows += 1
                    if raw_rows % 10_000_000 == 0:
                        print(f"Processed {raw_rows:,} interaction records...", flush=True)
                    problem_id = raw_row.get("problem_id")
                    if not isinstance(problem_id, str) or problem_id not in all_links:
                        try:
                            for field in ("log_id", "user_id", "problem_id"):
                                if not isinstance(raw_row.get(field), str) or not raw_row[field].strip():
                                    raise ValueError(f"missing_{field}")
                            _correct(raw_row.get("is_correct"))
                            if not is_valid_timestamp(raw_row.get("submit_time")):
                                raise ValueError("invalid_time")
                        except (ValueError, OverflowError, OSError) as error:
                            invalid += 1
                            issues.writerow(["interaction", str(raw_row.get("log_id", "")), str(error) or "invalid_record", "user-problem.json"])
                            continue
                        unmatched_count += 1
                        unmatched.writerow([raw_row["log_id"], raw_row["user_id"], problem_id, "no_concept_problem_link"])
                        continue
                    normalized = clean_interactions([raw_row], all_links)
                    if normalized.rejected:
                        invalid += 1
                        issue = normalized.rejected[0]
                        issues.writerow(["interaction", issue["log_id"], issue["reason"], "user-problem.json"])
                        continue
                    event = normalized.clean[0]
                    matched += 1
                    selected_concepts = sorted(set(event.concept_ids) & set(concept_names))
                    if not selected_concepts:
                        outside_domain += 1
                        continue
                    domain_matched += 1
                    multi_concept_rows += len(selected_concepts) > 1
                    score = _number(raw_row.get("score"))
                    attempts = raw_row.get("attempts")
                    try:
                        attempts = int(attempts) if attempts not in (None, "") else None
                        if attempts is not None and attempts < 0:
                            attempts = None
                            issues.writerow(["interaction", event.log_id, "invalid_attempts_metadata", "not expanded into events"])
                    except (ValueError, TypeError):
                        attempts = None
                        issues.writerow(["interaction", event.log_id, "invalid_attempts_metadata", "not expanded into events"])
                    if raw_row.get("score") not in (None, "") and score is None:
                        issues.writerow(["interaction", event.log_id, "invalid_score_metadata", "score omitted"])
                    values = (event.log_id, event.learner_id, event.problem_id, int(event.correct), score, attempts,
                              event.timestamp, json.dumps(selected_concepts, ensure_ascii=False))
                    previous = conn.execute("select learner_id,problem_id,is_correct,score,source_attempts,submitted_at,concept_ids from interaction where log_id=?", (event.log_id,)).fetchone()
                    if previous is not None:
                        if tuple(previous) == values[1:]:
                            duplicate_rows += 1
                        else:
                            issues.writerow(["interaction", event.log_id, "duplicate_log_id_conflict", "kept first stored row"])
                        continue
                    conn.execute("insert into interaction values(?,?,?,?,?,?,?,?)", values)
                    conn.execute("insert or ignore into learners values(?)", (event.learner_id,))
                    in_scope += 1
                    if in_scope % 10000 == 0:
                        conn.commit()
            conn.commit()

            selected = _selected_learners(conn, max_learners, seed)
            if selected is not None:
                conn.execute("create temp table selected_learner(id text primary key)")
                conn.executemany("insert into selected_learner values(?)", ((item,) for item in selected))
                count = conn.execute("select count(*) from interaction i join selected_learner l on l.id=i.learner_id").fetchone()[0]
                learner_count = len(selected)
            else:
                count = conn.execute("select count(*) from interaction").fetchone()[0]
                learner_count = conn.execute("select count(*) from learners").fetchone()[0]
            where = " join selected_learner l on l.id=i.learner_id" if selected is not None else ""
            learners_select = "select distinct i.learner_id from interaction i" + where + " order by i.learner_id"
            learner_stream, learner_writer = _write_csv(output / "learners.csv", ["id"])
            for (learner_id,) in conn.execute(learners_select):
                learner_writer.writerow([learner_id])
            learner_stream.close()

            train_index = int(count * train_ratio)
            validation_index = int(count * (train_ratio + validation_ratio))
            train_boundary_row = conn.execute("select i.submitted_at from interaction i" + where +
                                              " order by i.submitted_at,i.log_id limit 1 offset ?", (train_index,)).fetchone()
            validation_boundary_row = conn.execute("select i.submitted_at from interaction i" + where +
                                                   " order by i.submitted_at,i.log_id limit 1 offset ?", (validation_index,)).fetchone()
            train_cutoff = train_boundary_row[0] if train_boundary_row else None
            state_cutoff = validation_boundary_row[0] if validation_boundary_row else None
            split_counts = {name: 0 for name in ("train", "validation", "test")}
            split_bounds: dict[str, dict] = {name: {} for name in split_counts}
            train_stats: dict[str, list[int]] = {}
            concepts_with_history: set[str] = set()
            interactions_stream, interactions_writer = _write_csv(output / "interactions_clean.csv",
                    ["log_id", "learner_id", "problem_id", "is_correct", "score", "source_attempts", "submitted_at", "dataset_split"])
            sql = "select i.log_id,i.learner_id,i.problem_id,i.is_correct,i.score,i.source_attempts,i.submitted_at,i.concept_ids from interaction i" + where + " order by i.submitted_at,i.log_id"
            cursor = conn.execute(sql)
            for row in cursor:
                log_id, learner_id, problem_id, correct, score, attempts, submitted_at, concept_json = row
                split = split_for_timestamp(submitted_at, train_cutoff, state_cutoff) if train_cutoff and state_cutoff else "test"
                split_counts[split] += 1
                split_bounds[split].setdefault("first", submitted_at)
                split_bounds[split]["last"] = submitted_at
                interactions_writer.writerow([log_id, learner_id, problem_id, bool(correct), score if score is not None else "",
                                              attempts if attempts is not None else "", submitted_at, split])
                concept_list = json.loads(concept_json)
                concepts_with_history.update(concept_list)
                if split == "train":
                    for cid in concept_list:
                        values = train_stats.setdefault(cid, [0, 0])
                        values[0] += correct
                        values[1] += 1
                if state_cutoff is not None and submitted_at < state_cutoff:
                    for cid in concept_list:
                        conn.execute("""
                            insert into learner_state values(?,?,?,1)
                            on conflict(learner_id,concept_id) do update set
                              correct_count=learner_state.correct_count+excluded.correct_count,
                              total_count=learner_state.total_count+1
                            """, (learner_id, cid, correct))
            interactions_stream.close()

            if state_cutoff is None:
                last = conn.execute("select max(submitted_at) from interaction" + (" i join selected_learner l on l.id=i.learner_id" if selected is not None else "")).fetchone()[0]
                if last:
                    from datetime import datetime, timedelta
                    state_cutoff = (datetime.fromisoformat(last) + timedelta(microseconds=1)).isoformat(timespec="microseconds")
                else:
                    state_cutoff = "1970-01-01T00:00:00.000000+00:00"
            state_stream, state_writer = _write_csv(output / "learner_state.csv",
                    ["learner_id", "concept_id", "correct_count", "total_count", "mastery", "as_of"])
            state_rows = conn.execute("select learner_id,concept_id,correct_count,total_count from learner_state order by learner_id,concept_id")
            state_count = 0
            for learner_id, cid, correct, total in state_rows:
                state_writer.writerow([learner_id, cid, correct, total, correct / total, state_cutoff])
                state_count += 1
            state_stream.close()

            difficulty_stream, difficulty_writer = _write_csv(output / "concept_difficulty.csv",
                    ["concept_id", "train_correct", "train_total", "difficulty", "derived_from_split"])
            for cid in sorted(train_stats):
                correct, total = train_stats[cid]
                difficulty_writer.writerow([cid, correct, total, 1 - correct / total, "train"])
            difficulty_stream.close()
            conn.close()

        issues.writerow(["pipeline", "", "", "end"])
    finally:
        issue_stream.close()
        unmatched_stream.close()

    summary = {
        "source": "MOOCCubeX",
        "domain": domain,
        "random_seed": seed,
        "max_learners": max_learners,
        "split_ratios": {"train": train_ratio, "validation": validation_ratio, "test": 1 - train_ratio - validation_ratio},
        "concepts": len(concept_names),
        "concepts_with_history": len(concepts_with_history),
        "concepts_without_history": sorted(set(concept_names) - concepts_with_history),
        "problem_concept_rows": domain_link_rows,
        "duplicate_problem_concept_rows": relation_duplicates,
        "problems": len(domain_links),
        "prerequisite_rows": len(prerequisite_result.rows),
        "prerequisite_edges": len(prerequisite_result.edges),
        "prerequisite_endpoint_names": len(domain_names),
        "prerequisite_endpoint_names_resolved": len(resolution.name_to_id),
        "prerequisite_rows_unmapped_endpoint": skipped_unresolved_prerequisites,
        "interaction_raw_valid": matched + unmatched_count,
        "interactions_joined_any_concept": matched,
        "interactions_unmatched_any_concept": unmatched_count,
        "interactions_outside_domain": outside_domain,
        "interactions_with_domain_concept": domain_matched,
        "interactions_with_multiple_domain_concepts": multi_concept_rows,
        "interactions_invalid": invalid,
        "duplicate_stored_rows": duplicate_rows,
        "in_scope_interactions_before_learner_filter": in_scope,
        "selected_learners": learner_count,
        "interactions_clean": count,
        "learner_state_rows_at_test_start": state_count,
        "split_counts": split_counts,
        "split_bounds": split_bounds,
        "state_as_of": state_cutoff,
        "id_join_rate_all_valid_interactions": matched / (matched + unmatched_count) if matched + unmatched_count else None,
        "id_matching_rule": "exact unchanged problem_id and concept_id values; no prefix stripping or ID rewrites",
        "scope_rate_among_valid_interactions": domain_matched / (matched + unmatched_count) if matched + unmatched_count else None,
    }
    (output / "data_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output / "data_summary.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["key", "value"])
        for key, value in summary.items():
            writer.writerow([key, json.dumps(value, ensure_ascii=False)])
    (output / "pipeline_config.json").write_text(json.dumps({
        "domain": domain, "seed": seed, "max_learners": max_learners,
        "train_ratio": train_ratio, "validation_ratio": validation_ratio,
        "input_directory": str(raw), "streaming_json_chunk_bytes": 1024 * 1024,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/mooccubex"))
    parser.add_argument("--output", type=Path, default=Path("data/processed"))
    parser.add_argument("--staging", type=Path, default=Path("data/staging"))
    parser.add_argument("--domain", choices=("cs", "math", "psy"), default="cs")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-learners", type=int)
    parser.add_argument("--train-ratio", type=float, default=.70)
    parser.add_argument("--validation-ratio", type=float, default=.15)
    args = parser.parse_args()
    summary = _clean_payload(args.raw, args.output, args.staging, args.domain, args.seed,
                             args.max_learners, args.train_ratio, args.validation_ratio)
    print(json.dumps({key: summary[key] for key in ("domain", "concepts", "problems", "prerequisite_edges", "interactions_clean", "selected_learners", "split_counts")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
