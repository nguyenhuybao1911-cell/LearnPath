"""Streaming readers and conservative MOOCCubeX interaction normalization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, TextIO

from .planner import Interaction


def iter_json_records(path: str | Path, chunk_size: int = 1024 * 1024) -> Iterator[dict]:
    """Yield objects from a JSON array or JSON-lines file without loading it all."""
    decoder = json.JSONDecoder()
    with Path(path).open("r", encoding="utf-8") as stream:
        buffer = ""
        pos = 0
        eof = False
        array = None

        def more() -> None:
            nonlocal buffer, pos, eof
            if pos:
                buffer, pos = buffer[pos:], 0
            chunk = stream.read(chunk_size)
            eof = not chunk
            buffer += chunk

        while array is None:
            while pos >= len(buffer) and not eof:
                more()
            while pos < len(buffer) and buffer[pos].isspace():
                pos += 1
            if pos < len(buffer):
                array = buffer[pos] == "["
                if array:
                    pos += 1
            elif eof:
                return

        while True:
            while True:
                while pos < len(buffer) and (buffer[pos].isspace() or (array and buffer[pos] == ",")):
                    pos += 1
                if pos < len(buffer):
                    break
                if eof:
                    if array:
                        raise ValueError("unterminated JSON array")
                    return
                more()
            if array and buffer[pos] == "]":
                return
            try:
                record, end = decoder.raw_decode(buffer, pos)
            except json.JSONDecodeError:
                if eof:
                    raise
                more()
                continue
            if not isinstance(record, dict):
                raise ValueError("interaction JSON must contain objects")
            yield record
            pos = end


@dataclass(frozen=True)
class CleanInteraction:
    learner_id: str
    problem_id: str
    correct: bool
    timestamp: str
    log_id: str
    concept_ids: frozenset[str]

    def as_interaction(self) -> Interaction:
        return Interaction(self.learner_id, self.problem_id, self.correct, datetime.fromisoformat(self.timestamp), self.log_id)


@dataclass
class IngestResult:
    clean: list[CleanInteraction]
    rejected: list[dict[str, str]]
    duplicate_rows: int
    unmatched_rows: int


def _timestamp(value: object) -> str:
    if isinstance(value, bool) or value is None:
        raise ValueError("invalid_time")
    if isinstance(value, (int, float)):
        seconds = float(value)
        if abs(seconds) >= 100_000_000_000:
            seconds /= 1000
        result = datetime.fromtimestamp(seconds, tz=timezone.utc)
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            seconds = float(text)
        except ValueError:
            seconds = None
        if seconds is not None:
            return _timestamp(seconds)
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        else:
            result = result.astimezone(timezone.utc)
    else:
        raise ValueError("invalid_time")
    return result.astimezone(timezone.utc).isoformat(timespec="microseconds")


def is_valid_timestamp(value: object) -> bool:
    """Validate source timestamps, using a cheap exact check for MOOCCubeX's naive format."""
    if isinstance(value, str):
        text = value.strip()
        if (len(text) == 19 and text[4] == "-" and text[7] == "-" and text[10] in (" ", "T")
                and text[13] == ":" and text[16] == ":"
                and all("0" <= text[index] <= "9" for index in (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18))):
            year, month, day = int(text[:4]), int(text[5:7]), int(text[8:10])
            hour, minute, second = int(text[11:13]), int(text[14:16]), int(text[17:19])
            if year < 1 or not 1 <= month <= 12 or not 0 <= hour <= 23 or not 0 <= minute <= 59 or not 0 <= second <= 59:
                return False
            leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
            month_days = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
            return 1 <= day <= month_days[month - 1]
    try:
        _timestamp(value)
        return True
    except (ValueError, OverflowError, OSError, TypeError):
        return False


def _correct(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.lower() in ("true", "false", "0", "1"):
        return value.lower() in ("true", "1")
    raise ValueError("invalid_correctness")


def clean_interactions(records: Iterable[dict], problem_concepts: dict[str, set[str]]) -> IngestResult:
    clean: list[CleanInteraction] = []
    rejected: list[dict[str, str]] = []
    seen: dict[str, CleanInteraction] = {}
    duplicates = unmatched = 0
    for row in records:
        try:
            for field in ("log_id", "user_id", "problem_id"):
                if not isinstance(row.get(field), str) or not row[field].strip():
                    raise ValueError(f"missing_{field}")
            event = CleanInteraction(
                row["user_id"], row["problem_id"], _correct(row.get("is_correct")),
                _timestamp(row.get("submit_time")), row["log_id"],
                frozenset(problem_concepts.get(row["problem_id"], set())),
            )
        except (ValueError, OverflowError, OSError) as error:
            rejected.append({"log_id": str(row.get("log_id", "")), "reason": str(error) or "invalid_record"})
            continue
        previous = seen.get(event.log_id)
        if previous is not None:
            if previous == event:
                duplicates += 1
            else:
                rejected.append({"log_id": event.log_id, "reason": "duplicate_log_id_conflict"})
            continue
        seen[event.log_id] = event
        clean.append(event)
        unmatched += not event.concept_ids
    return IngestResult(clean, rejected, duplicates, unmatched)
