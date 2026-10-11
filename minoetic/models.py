"""Shared values; no configuration or credentials are discovered."""
from dataclasses import dataclass
from datetime import datetime, timezone

JsonObject = dict[str, object]


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def stamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    state: str


@dataclass(frozen=True)
class Project:
    project_id: str
    as_of: datetime
    summary: str


@dataclass(frozen=True)
class Tasks:
    project_id: str
    as_of: datetime
    tasks: tuple[Task, ...]


@dataclass(frozen=True)
class Check:
    id: str
    state: str
    reason: str
    source: str | None = None
    field: str | None = None


class Problem(Exception):
    def __init__(self, reason: str, state: str = "failed",
                 source: str | None = None, field: str | None = None):
        super().__init__(reason)
        self.reason, self.state, self.source, self.field = reason, state, source, field
