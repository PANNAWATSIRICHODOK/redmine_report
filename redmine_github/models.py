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
