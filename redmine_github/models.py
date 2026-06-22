from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Commit:
    short_sha: str
    sha: str
    date: str
    subject: str
    body: str
    files_changed: int = 0
    lines_changed: int = 0
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class IssueDraft:
    subject: str
    description: str
    note: str = ""
    assigned_to_id: int | None = None
    status_id: int | None = None
    done_ratio: int | None = None
    estimated_hours: float | None = None
    spent_hours: float | None = None
    ai_score: float | None = None
    custom_fields: list[dict[str, object]] | None = None
