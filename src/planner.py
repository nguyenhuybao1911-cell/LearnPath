"""Deterministic Greedy Best-First planner for prerequisite concept graphs."""

from __future__ import annotations

import heapq
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Concept:
    id: str
    name: str


@dataclass(frozen=True)
class Edge:
    prerequisite: str
    concept: str


@dataclass(frozen=True)
class Interaction:
    learner_id: str
    problem_id: str
    correct: bool
    submitted_at: datetime
    log_id: str


@dataclass(frozen=True)
class Mastery:
    correct: int
    total: int
    as_of: datetime

    @property
    def value(self) -> float:
        return self.correct / self.total


@dataclass(frozen=True)
class Weights:
    p: float = 0.0
    n: float = 0.35
    d: float = 0.25
    r: float = 0.40

    def __post_init__(self) -> None:
        values = (self.p, self.n, self.d, self.r)
        if any(not math.isfinite(v) or v < 0 for v in values) or not math.isclose(sum(values), 1.0, abs_tol=1e-9):
            raise ValueError("heuristic weights must be finite, nonnegative, and sum to 1")


@dataclass(frozen=True)
class Breakdown:
    p: float
    n: float
    d: float
    r: float
    h: float
    mastery: float | None
    explanation: str


@dataclass(frozen=True)
class PlanStep:
    concept_id: str
    concept_name: str
    scores: Breakdown


@dataclass(frozen=True)
class Recommendation:
    learner_id: str
    target_id: str
    status: str
    steps: tuple[PlanStep, ...] = ()
    expanded: int = 0
    message: str = ""
    peak_open: int = 0


def learner_state_at(
    interactions: list[Interaction], problem_concepts: dict[str, set[str]], learner_id: str, as_of: datetime
) -> dict[str, Mastery]:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in interactions:
        if row.learner_id == learner_id and row.submitted_at < as_of:
            for concept_id in problem_concepts.get(row.problem_id, ()):
                counts[concept_id][1] += 1
                counts[concept_id][0] += int(row.correct)
    return {cid: Mastery(ok, total, as_of) for cid, (ok, total) in counts.items()}


def _validate_graph(concepts: dict[str, Concept], edges: list[Edge]) -> dict[str, set[str]]:
    prerequisites: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    indegree = {cid: 0 for cid in concepts}
    for edge in set(edges):
        if edge.prerequisite not in concepts or edge.concept not in concepts:
            raise ValueError(f"unknown concept in prerequisite edge: {edge}")
        if edge.prerequisite == edge.concept:
            raise ValueError(f"self-loop in prerequisite graph: {edge.prerequisite}")
        prerequisites[edge.concept].add(edge.prerequisite)
        outgoing[edge.prerequisite].add(edge.concept)
        indegree[edge.concept] += 1
    queue = deque(sorted(cid for cid, degree in indegree.items() if degree == 0))
    visited = 0
    while queue:
        cid = queue.popleft()
        visited += 1
        for child in sorted(outgoing[cid]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(concepts):
        raise ValueError("cycle in prerequisite graph")
    return prerequisites


def _distances_to_target(target: str, prerequisites: dict[str, set[str]]) -> dict[str, int]:
    reverse: dict[str, set[str]] = defaultdict(set)
    for child, parents in prerequisites.items():
        for parent in parents:
            reverse[child].add(parent)
    distances = {target: 0}
    queue = deque([target])
    while queue:
        child = queue.popleft()
        for parent in sorted(reverse[child]):
            if parent not in distances:
                distances[parent] = distances[child] + 1
                queue.append(parent)
    return distances


def recommend(
    learner_id: str,
    target_id: str,
    concepts: dict[str, Concept],
    edges: list[Edge],
    mastery: dict[str, Mastery],
    difficulty: dict[str, float],
    *,
    tau: float = 0.7,
    min_interactions: int = 2,
    weights: Weights = Weights(),
    max_states: int = 10_000,
    time_limit_seconds: float = 2.0,
    allowed_concepts: set[str] | None = None,
) -> Recommendation:
    if target_id not in concepts:
        raise ValueError(f"unknown target concept: {target_id}")
    if not 0 <= tau <= 1 or min_interactions < 0 or max_states < 1 or time_limit_seconds <= 0:
        raise ValueError("invalid search or mastery limits")
    prereqs = _validate_graph(concepts, edges)
    distances = _distances_to_target(target_id, prereqs)
    initial = frozenset(
        cid for cid, value in mastery.items()
        if cid in concepts and value.total >= min_interactions and value.value >= tau
    )
    if target_id in initial:
        return Recommendation(learner_id, target_id, "target_already_mastered", message="Mục tiêu đã đạt ngưỡng thành thạo từ dữ liệu quan sát.")
    if target_id not in distances:
        return Recommendation(learner_id, target_id, "no_path", message="Không có đường prerequisite tới mục tiêu.")
    allowed = set(concepts) if allowed_concepts is None else allowed_concepts
    if target_id not in allowed:
        return Recommendation(learner_id, target_id, "no_path", message="Mục tiêu nằm ngoài phạm vi được chọn.")

    observed = [x.value for x in mastery.values() if x.total]
    ability = sum(observed) / len(observed) if observed else 0.5

    def score(cid: str, completed: frozenset[str]) -> Breakdown:
        parents = prereqs.get(cid, set())
        p = len(parents & completed) / len(parents) if parents else 1.0
        record = mastery.get(cid)
        m = record.value if record and record.total else None
        n = 1.0 - (m if m is not None else 0.5)
        d_est = min(1.0, max(0.0, difficulty.get(cid, 0.5)))
        d = 1.0 - abs(d_est - ability)
        r = 1.0 / (1 + distances[cid])
        h = weights.p * p + weights.n * n + weights.d * d + weights.r * r
        status = "chưa có dữ liệu" if m is None else f"mastery quan sát {m:.2f}"
        return Breakdown(p, n, d, r, h, m, f"Prerequisite sẵn sàng ({p:.0%}); {status}; độ phù hợp độ khó {d:.2f}; cách mục tiêu {distances[cid]} cạnh.")

    start = time.monotonic()
    # Greedy Best-First: order by score of last addition; score/id/path break ties deterministically.
    open_states: list[tuple[float, str, tuple[str, ...], frozenset[str]]] = []
    seen: set[tuple[str, ...]] = {()}

    def add_children(path: tuple[str, ...], completed: frozenset[str]) -> None:
        eligible = [
            cid for cid in distances
            if cid in allowed and cid not in completed and prereqs.get(cid, set()) <= completed
        ]
        for cid in sorted(eligible):
            new_path = path + (cid,)
            if new_path in seen:
                continue
            seen.add(new_path)
            breakdown = score(cid, completed)
            heapq.heappush(open_states, (-breakdown.h, cid, new_path, completed | {cid}))

    add_children((), initial)
    peak_open = len(open_states)
    expanded = 0
    while open_states and expanded < max_states and time.monotonic() - start < time_limit_seconds:
        _, _, path, completed = heapq.heappop(open_states)
        expanded += 1
        if target_id in completed:
            steps = tuple(PlanStep(cid, concepts[cid].name, score(cid, initial | set(path[:i]))) for i, cid in enumerate(path))
            return Recommendation(learner_id, target_id, "reached", steps, expanded, "Đã tìm thấy lộ trình hợp lệ bằng Greedy Best-First; đây không phải bảo đảm tối ưu toàn cục.", peak_open)
        add_children(path, completed)
        peak_open = max(peak_open, len(open_states))
    status = "budget_exhausted" if open_states else "no_path"
    message = "Hết ngân sách trạng thái/thời gian tìm kiếm." if open_states else "Không tìm thấy lộ trình thỏa prerequisite."
    return Recommendation(learner_id, target_id, status, expanded=expanded, message=message, peak_open=peak_open)
