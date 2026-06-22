from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Commit:
    short_sha: str
    sha: str
    date: str
    subject: str
    body: str


@dataclass(frozen=True)
class IssueDraft:
    subject: str
    description: str
    assigned_to_id: int | None = None
    status_id: int | None = None
    done_ratio: int | None = None
    estimated_hours: float | None = None
    spent_hours: float | None = None
    ai_score: int | None = None
    custom_fields: list[dict[str, object]] | None = None
