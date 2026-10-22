"""Validation tuning and time-split baselines using only the normalized dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sqlite3
import statistics
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from .planner import Concept, Edge, Mastery, Weights, recommend

METHODS = ("fixed_eligible", "random_eligible", "best_first_heuristic")
WEIGHT_GRID = (
    (0.0, .60, .20, .20), (0.0, .50, .20, .30), (0.0, .35, .25, .40),
    (0.0, .20, .20, .60), (0.0, .25, .45, .30), (0.0, .10, .40, .50),
)


def ranking_metrics(route: list[str], future_concepts: set[str], k: int) -> dict[str, float | None]:
    if k < 1:
        raise ValueError("K must be positive")
    if not future_concepts:
        return {"precision": None, "recall": None, "ndcg": None}
    ranked = route[:k]
    hits = [1 if concept in future_concepts else 0 for concept in ranked]
    precision = sum(hits) / max(1, len(ranked))
    recall = sum(hits) / len(future_concepts)
    dcg = sum(hit / math.log2(index + 2) for index, hit in enumerate(hits))
    ideal_hits = min(k, len(future_concepts))
    ideal = sum(1 / math.log2(index + 2) for index in range(ideal_hits))
    return {"precision": precision, "recall": recall, "ndcg": dcg / ideal if ideal else 0.0}


def _scope(target: str, edges: list[Edge]) -> tuple[set[str], dict[str, set[str]]]:
    parents: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        parents[edge.concept].add(edge.prerequisite)
    required = {target}
    pending = [target]
    while pending:
        for parent in parents.get(pending.pop(), ()):
            if parent not in required:
                required.add(parent)
                pending.append(parent)
    return required, parents


def eligible_plan(target: str, concepts: dict[str, Concept], edges: list[Edge], mastered: set[str],
                  *, strategy: str, seed: int = 0) -> list[str]:
    if strategy not in ("fixed", "random"):
        raise ValueError("strategy must be fixed or random")
    required, parents = _scope(target, edges)
    if target not in concepts or not required <= set(concepts):
        return []
    completed = set(mastered)
    route: list[str] = []
    rng = random.Random(seed)
    while target not in completed:
        candidates = sorted(cid for cid in required - completed if parents.get(cid, set()) <= completed)
        if not candidates:
            return []
        selected = candidates[0] if strategy == "fixed" else rng.choice(candidates)
        completed.add(selected)
        route.append(selected)
    return route


def mastered_at_threshold(state: dict[str, Mastery], tau: float, min_interactions: int) -> set[str]:
    """Use one observed-history threshold consistently across all evaluation methods."""
    return {cid for cid, row in state.items() if row.total >= min_interactions and row.value >= tau}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def _load_data(data_dir: Path) -> tuple[dict[str, Concept], list[Edge], dict[str, set[str]], dict[str, float], dict]:
    summary = json.loads((data_dir / "data_summary.json").read_text(encoding="utf-8"))
    concepts = {row["id"]: Concept(row["id"], row["name"]) for row in _read_csv(data_dir / "concepts.csv")}
    edges = [Edge(row["prerequisite_id"], row["concept_id"]) for row in _read_csv(data_dir / "prerequisites.csv")
             if row["annotated"].lower() == "true" and row["ground_truth"] == "1"]
    problem_concepts: dict[str, set[str]] = defaultdict(set)
    for row in _read_csv(data_dir / "problem_concepts.csv"):
        problem_concepts[row["problem_id"]].add(row["concept_id"])
    difficulty = {row["concept_id"]: float(row["difficulty"]) for row in _read_csv(data_dir / "concept_difficulty.csv")}
    required = {"data_summary.json", "concepts.csv", "prerequisites.csv", "problem_concepts.csv", "interactions_clean.csv", "concept_difficulty.csv"}
    missing = sorted(name for name in required if not (data_dir / name).is_file())
    if missing:
        raise FileNotFoundError("Missing processed files: " + ", ".join(missing))
    if not concepts or not edges or not problem_concepts:
        raise ValueError("Processed dataset has no concepts, annotated prerequisite edges, or problem-concept links")
    return concepts, edges, dict(problem_concepts), difficulty, summary


def _stage_interactions(data_dir: Path, connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE interaction(learner_id TEXT, problem_id TEXT, is_correct INTEGER, submitted_at TEXT,
                                 dataset_split TEXT, log_id TEXT PRIMARY KEY);
        CREATE INDEX interaction_learner_time_idx ON interaction(learner_id, submitted_at, log_id);
        CREATE INDEX interaction_split_time_idx ON interaction(dataset_split, submitted_at);
    """)
    path = data_dir / "interactions_clean.csv"
    with path.open("r", newline="", encoding="utf-8-sig") as stream, connection:
        for row in csv.DictReader(stream):
            connection.execute("insert into interaction values(?,?,?,?,?,?)", (
                row["learner_id"], row["problem_id"], int(row["is_correct"].lower() in ("true", "1")),
                row["submitted_at"], row["dataset_split"], row["log_id"],
            ))


def _learner_sample(connection: sqlite3.Connection, maximum: int, seed: int, before: str | None = None) -> list[str]:
    entries = []
    query = "select distinct learner_id from interaction"
    parameters: tuple[str, ...] = ()
    if before is not None:
        query += " where submitted_at < ?"
        parameters = (before,)
    for (learner,) in connection.execute(query, parameters):
        key = int.from_bytes(hashlib.sha256(f"{seed}:{learner}".encode()).digest()[:8], "big")
        entries.append((key, learner))
    return [learner for _, learner in sorted(entries)[:maximum]]


def _mastery(connection: sqlite3.Connection, learner: str, cutoff: str, links: dict[str, set[str]]) -> tuple[dict[str, Mastery], set[str]]:
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for problem, correct in connection.execute(
            "select problem_id,is_correct from interaction where learner_id=? and submitted_at < ? order by submitted_at,log_id",
            (learner, cutoff)):
        for cid in links.get(problem, ()):
            totals[cid][1] += 1
            totals[cid][0] += correct
    as_of = datetime.fromisoformat(cutoff)
    state = {cid: Mastery(correct, total, as_of) for cid, (correct, total) in totals.items()}
    return state, {cid for cid, row in state.items() if row.total > 0}


def _future(connection: sqlite3.Connection, learner: str, cutoff: str, window_days: int,
            split: str, links: dict[str, set[str]]) -> tuple[set[str], list[str]]:
    end = datetime.fromisoformat(cutoff) + timedelta(days=window_days)
    found: set[str] = set()
    sequence: list[str] = []
    for (problem,) in connection.execute("""
            select problem_id from interaction where learner_id=? and dataset_split=?
              and submitted_at >= ? and submitted_at < ? order by submitted_at,log_id
            """, (learner, split, cutoff, end.isoformat(timespec="microseconds"))):
        for cid in sorted(links.get(problem, ())):
            if cid not in found:
                found.add(cid)
                sequence.append(cid)
    return found, sequence


def _target(concepts: dict[str, Concept], edges: list[Edge], requested: str | None) -> str:
    if requested:
        if requested not in concepts:
            raise ValueError(f"Target not found in processed concepts: {requested}")
        return requested
    children = {edge.prerequisite for edge in edges}
    sinks = sorted(set(concepts) - children)
    if not sinks:
        raise ValueError("No prerequisite graph sink available as target")
    return sinks[0]


def _baseline(target: str, concepts: dict[str, Concept], edges: list[Edge], mastered: set[str],
              strategy: str, seed: int, max_states: int, time_limit: float) -> tuple[str, list[str], int]:
    if target in mastered:
        return "target_already_mastered", [], 0
    required, parents = _scope(target, edges)
    if not required <= set(concepts):
        return "no_path", [], 0
    done = set(mastered)
    route: list[str] = []
    rng = random.Random(seed)
    start = time.perf_counter()
    expanded = 0
    while target not in done and expanded < max_states and time.perf_counter() - start < time_limit:
        available = sorted(cid for cid in required - done if parents.get(cid, set()) <= done)
        if not available:
            return "no_path", [], expanded
        selected = available[0] if strategy == "fixed" else rng.choice(available)
        route.append(selected)
        done.add(selected)
        expanded += 1
    if target in done:
        return "reached", route, expanded
    if expanded >= max_states or time.perf_counter() - start >= time_limit:
        return "budget_exhausted", [], expanded
    return "no_path", [], expanded


def _route_metrics(route: list[str], status: str, expanded: int, runtime_ms: float, future: set[str],
                   future_sequence: list[str], edges: list[Edge], mastered: set[str], k: int) -> dict:
    ranking = ranking_metrics(route, future, k)
    done = set(mastered)
    parent_map: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        parent_map[edge.concept].add(edge.prerequisite)
    total_prereq = violations = 0
    for cid in route:
        for parent in parent_map.get(cid, ()):
            total_prereq += 1
            violations += parent not in done
        done.add(cid)
    return {
        "precision_at_k": ranking["precision"],
        "recall_at_k": ranking["recall"],
        "ndcg_at_k": ranking["ndcg"],
        "prerequisite_violation_rate": violations / total_prereq if total_prereq else 0.0,
        "goal_route_rate": int(status in ("reached", "target_already_mastered")),
        "runtime_ms": runtime_ms,
        "expanded_states": expanded,
        "route_length": len(route),
        "future_concepts": len(future),
        "next_step_accuracy": None if not future_sequence else int(bool(route) and route[0] == future_sequence[0]),
    }


def _tune(data_dir: Path, concepts: dict[str, Concept], edges: list[Edge], links: dict[str, set[str]],
          difficulty: dict[str, float], summary: dict, target: str, k: int, horizon: int,
          seed: int, max_learners: int, max_states: int, time_limit_ms: int) -> dict:
    cutoff = summary.get("split_bounds", {}).get("validation", {}).get("first")
    if not cutoff:
        raise ValueError("No validation split cutoff; cannot tune configuration")
    with tempfile.TemporaryDirectory(prefix="learnpath-eval-") as directory:
        connection = sqlite3.connect(Path(directory) / "eval.sqlite3")
        _stage_interactions(data_dir, connection)
        learners = _learner_sample(connection, max_learners, seed, cutoff)
        future_by_learner = {learner: _future(connection, learner, cutoff, horizon, "validation", links) for learner in learners}
        if not any(future for future, _ in future_by_learner.values()):
            raise ValueError("Validation future window has no observed concepts; tau and weights cannot be selected from this split")
        grid_rows = []
        best = None
        for tau in (.5, .6, .7, .8):
            for minimum in (1, 2, 3):
                for components in WEIGHT_GRID:
                    weights = Weights(*components)
                    scores = []
                    for learner in learners:
                        future, _ = future_by_learner[learner]
                        if not future:
                            continue
                        state, _ = _mastery(connection, learner, cutoff, links)
                        route = recommend(learner, target, concepts, edges, state, difficulty, tau=tau,
                                          min_interactions=minimum, weights=weights, max_states=max_states,
                                          time_limit_seconds=time_limit_ms / 1000)
                        scores.append(ranking_metrics([step.concept_id for step in route.steps], future, k)["ndcg"] or 0.0)
                    mean_score = statistics.fmean(scores) if scores else float("nan")
                    row = {"tau": tau, "min_interactions": minimum, "wP": components[0], "wN": components[1],
                           "wD": components[2], "wR": components[3], "mean_ndcg_at_k": mean_score, "learners": len(scores)}
                    grid_rows.append(row)
                    order = (mean_score, -tau, -minimum, tuple(-x for x in components))
                    if best is None or order > best[0]:
                        best = order, row
        connection.close()
    with (data_dir / "validation_grid.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(grid_rows[0]))
        writer.writeheader()
        writer.writerows(grid_rows)
    if best is None:
        raise ValueError("No validation parameters could be evaluated")
    selected = best[1]
    return {
        "locked": True, "selected_on": "validation", "domain": summary["domain"], "target_id": target,
        "tau": selected["tau"], "min_interactions": selected["min_interactions"],
        "weights": {"p": selected["wP"], "n": selected["wN"], "d": selected["wD"], "r": selected["wR"]},
        "validation_ndcg_at_k": selected["mean_ndcg_at_k"], "validation_learners": selected["learners"],
        "top_k": k, "future_window_days": horizon, "sample_max_learners": max_learners,
        "seed": seed, "random_runs": 20, "max_states": max_states, "time_limit_ms": time_limit_ms,
        "tie_break": "concept ID ascending, then path tuple ascending",
    }


def _test_run(data_dir: Path, concepts: dict[str, Concept], edges: list[Edge], links: dict[str, set[str]],
              difficulty: dict[str, float], summary: dict, config: dict) -> tuple[list[dict], dict[str, list[dict]]]:
    cutoff = summary.get("split_bounds", {}).get("test", {}).get("first")
    if not cutoff:
        raise ValueError("No test split cutoff; cannot run final evaluation")
    weights = Weights(**config["weights"])
    with tempfile.TemporaryDirectory(prefix="learnpath-eval-") as directory:
        connection = sqlite3.connect(Path(directory) / "eval.sqlite3")
        _stage_interactions(data_dir, connection)
        learners = _learner_sample(connection, config["sample_max_learners"], config["seed"], cutoff)
        rows: list[dict] = []
        step_rows: dict[str, list[dict]] = defaultdict(list)
        random_seeds = range(config["seed"], config["seed"] + config["random_runs"])
        for learner in learners:
            state, _observed = _mastery(connection, learner, cutoff, links)
            mastered = mastered_at_threshold(state, config["tau"], config["min_interactions"])
            future, future_sequence = _future(connection, learner, cutoff, config["future_window_days"], "test", links)
            outputs = []
            start = time.perf_counter()
            status, route, expanded = _baseline(config["target_id"], concepts, edges, mastered, "fixed",
                                                config["seed"], config["max_states"], config["time_limit_ms"] / 1000)
            outputs.append(("fixed_eligible", config["seed"], status, route, expanded, (time.perf_counter() - start) * 1000))
            for run_seed in random_seeds:
                start = time.perf_counter()
                status, route, expanded = _baseline(config["target_id"], concepts, edges, mastered, "random",
                                                    run_seed + int.from_bytes(hashlib.sha256(learner.encode()).digest()[:4], "big"),
                                                    config["max_states"], config["time_limit_ms"] / 1000)
                outputs.append(("random_eligible", run_seed, status, route, expanded, (time.perf_counter() - start) * 1000))
            start = time.perf_counter()
            best = recommend(learner, config["target_id"], concepts, edges, state, difficulty,
                             tau=config["tau"], min_interactions=config["min_interactions"], weights=weights,
                             max_states=config["max_states"], time_limit_seconds=config["time_limit_ms"] / 1000)
            outputs.append(("best_first_heuristic", config["seed"], best.status,
                            [step.concept_id for step in best.steps], best.expanded, (time.perf_counter() - start) * 1000))
            for method, run_seed, route_status, route, expanded_states, runtime in outputs:
                metrics = _route_metrics(route, route_status, expanded_states, runtime, future, future_sequence,
                                         edges, mastered, config["top_k"])
                rows.append({"learner_id": learner, "method": method, "run_seed": run_seed,
                             "target_id": config["target_id"], "status": route_status, **metrics})
                step_rows[method].append({"learner_id": learner, "method": method, "run_seed": run_seed,
                                          "next_step_accuracy": metrics["next_step_accuracy"]})
        connection.close()
    return rows, step_rows


def _std(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) > 1 else (0.0 if values else None)


def _summarize(rows: list[dict]) -> list[dict]:
    metrics = ("precision_at_k", "recall_at_k", "ndcg_at_k", "prerequisite_violation_rate", "goal_route_rate", "runtime_ms", "expanded_states", "route_length")
    output = []
    for method in METHODS:
        method_rows = [row for row in rows if row["method"] == method]
        for metric in metrics:
            values = [float(row[metric]) for row in method_rows if row[metric] is not None]
            learner_values: dict[str, list[float]] = defaultdict(list)
            seed_values: dict[int, list[float]] = defaultdict(list)
            for row in method_rows:
                if row[metric] is not None:
                    learner_values[row["learner_id"]].append(float(row[metric]))
                    seed_values[row["run_seed"]].append(float(row[metric]))
            learner_means = [statistics.fmean(values) for values in learner_values.values()]
            seed_means = [statistics.fmean(values) for values in seed_values.values()]
            within_seed_sd = [_std(values) for values in learner_values.values() if len(values) > 1]
            output.append({
                "method": method, "metric": metric,
                "mean": statistics.fmean(values) if values else None,
                "std_across_learners": _std(learner_means),
                "std_between_random_runs": _std(seed_means) if method == "random_eligible" else 0.0,
                "mean_within_learner_seed_sd": statistics.fmean(within_seed_sd) if within_seed_sd else 0.0,
                "learners": len(learner_values), "observations": len(values),
            })
    return output


def _write_svg(path: Path, summary_rows: list[dict]) -> None:
    values = {row["method"]: row["mean"] for row in summary_rows if row["metric"] == "ndcg_at_k"}
    methods = list(METHODS)
    width, height = 720, 320
    bars = []
    for index, method in enumerate(methods):
        value = values.get(method)
        if value is None:
            continue
        y = 56 + index * 78
        bar_width = max(2, min(500, float(value) * 500))
        label = method.replace("_", " ")
        bars.append(f'<text x="24" y="{y+20}" font-size="13">{label}</text><rect x="205" y="{y}" width="{bar_width:.1f}" height="30" rx="5" fill="#4c846d"/><text x="{215+bar_width:.1f}" y="{y+20}" font-size="12">{float(value):.3f}</text>')
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#fbfaf7"/><text x="24" y="30" font-size="15" font-family="sans-serif">NDCG@K · test</text>{"".join(bars)}</svg>', encoding="utf-8")


def run(data_dir: Path, mode: str, target_arg: str | None, k: int, horizon: int, seed: int,
        max_learners: int, random_runs: int, max_states: int, time_limit_ms: int) -> None:
    concepts, edges, links, difficulty, summary = _load_data(data_dir)
    target = _target(concepts, edges, target_arg)
    if mode == "tune":
        config = _tune(data_dir, concepts, edges, links, difficulty, summary, target, k, horizon, seed,
                       max_learners, max_states, time_limit_ms)
        config["random_runs"] = random_runs
        (data_dir / "experiment_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({key: config[key] for key in ("target_id", "tau", "min_interactions", "weights", "validation_ndcg_at_k")}, ensure_ascii=False, indent=2))
        return
    config_path = data_dir / "experiment_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("locked") is not True or config.get("selected_on") != "validation":
        raise ValueError("Final test requires a locked configuration selected on validation")
    if target_arg is not None and target_arg != config["target_id"]:
        raise ValueError("Test target differs from the target locked before the final test")
    rows, step_rows = _test_run(data_dir, concepts, edges, links, difficulty, summary, config)
    fields = ["learner_id", "method", "run_seed", "target_id", "status", "precision_at_k", "recall_at_k", "ndcg_at_k", "prerequisite_violation_rate", "goal_route_rate", "runtime_ms", "expanded_states", "route_length", "future_concepts", "next_step_accuracy"]
    with (data_dir / "per_learner_results.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary_rows = _summarize(rows)
    with (data_dir / "summary_results.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)
    with (data_dir / "summary_next_step.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["method", "mean_next_step_accuracy", "std_across_learners", "std_between_random_runs", "observations"])
        for method in METHODS:
            group = [row for row in step_rows[method] if row["next_step_accuracy"] is not None]
            by_learner: dict[str, list[float]] = defaultdict(list)
            for row in group:
                by_learner[row["learner_id"]].append(float(row["next_step_accuracy"]))
            learner_means = [statistics.fmean(values) for values in by_learner.values()]
            by_seed: dict[int, list[float]] = defaultdict(list)
            for row in group:
                by_seed[row["run_seed"]].append(float(row["next_step_accuracy"]))
            seed_means = [statistics.fmean(values) for values in by_seed.values()]
            writer.writerow([method, statistics.fmean(learner_means) if learner_means else "", _std(learner_means),
                             _std(seed_means) if method == "random_eligible" else 0, len(group)])
    _write_svg(data_dir / "results_ndcg.svg", summary_rows)
    (data_dir / "experiment_report.md").write_text(
        "# Báo cáo đánh giá LearnPath\n\n"
        f"- Target cố định trước test: `{config['target_id']}`.\n"
        f"- Test cutoff: `{summary.get('split_bounds', {}).get('test', {}).get('first')}`; cửa sổ ground truth: {config['future_window_days']} ngày.\n"
        f"- K = {config['top_k']}; Precision@K chia cho `min(K, độ dài route)`; ground truth rỗng cho metric ranking = NA.\n"
        "- Target chỉ chọn từ graph prerequisite; learner state tại cutoff chỉ dùng các tương tác có timestamp nhỏ hơn cutoff.\n"
        "- Nhánh kế hoạch giả định concept đã thêm được hoàn thành; không cập nhật mastery quan sát.\n"
        "- Các tương tác tương lai không quan sát không được coi là bằng chứng concept không hữu ích. Kết quả lịch sử không chứng minh learning gain.\n"
        "- Random Eligible chạy nhiều seed; báo cáo độ lệch chuẩn giữa learner và giữa các seed ở các cột riêng.\n"
        "- Fixed Eligible chọn ID nhỏ nhất trong tập hợp lệ hiện tại; Random Eligible chọn ngẫu nhiên trong cùng tập; Best-First dùng cấu hình khóa từ validation.\n",
        encoding="utf-8")
    print(f"Wrote results for {len({row['learner_id'] for row in rows})} learners to {data_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/processed"))
    parser.add_argument("--mode", choices=("tune", "test"), required=True)
    parser.add_argument("--target")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--horizon-days", type=int, default=14)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-learners", type=int, default=500)
    parser.add_argument("--random-runs", type=int, default=20)
    parser.add_argument("--max-states", type=int, default=10_000)
    parser.add_argument("--time-limit-ms", type=int, default=2_000)
    args = parser.parse_args()
    if args.k < 1 or args.horizon_days < 1 or args.max_learners < 1 or args.random_runs < 1:
        parser.error("K, horizon, max learners and random runs must be positive")
    run(args.data, args.mode, args.target, args.k, args.horizon_days, args.seed,
        args.max_learners, args.random_runs, args.max_states, args.time_limit_ms)


if __name__ == "__main__":
    main()
