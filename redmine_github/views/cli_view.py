from __future__ import annotations

from typing import Any

from redmine_github.models import IssueDraft


def print_no_commits() -> None:
    print("No commits found.")


def format_hours(value: float | None) -> str:
    if value is None:
        return "-"
    rounded = round(value, 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def draft_summary(draft: IssueDraft) -> str:
    estimated = format_hours(draft.estimated_hours)
    ai = format_hours(draft.ai_score)
    spent = format_hours(draft.spent_hours)
    return (
        f"estimated={estimated}h "
        f"ai={ai if ai == '-' else ai + 'h'} "
        f"spent={spent}h"
    )


def print_dry_run(draft: IssueDraft) -> None:
    print(f"DRY RUN: {draft.subject} ({draft_summary(draft)})")


def print_created(issue: dict[str, Any], draft: IssueDraft) -> None:
    print(f"created #{issue.get('id')}: {draft.subject} ({draft_summary(draft)})")


def print_skipped_existing(issue: dict[str, Any], draft: IssueDraft) -> None:
    print(f"skipped existing #{issue.get('id')}: {draft.subject} ({draft_summary(draft)})")


def print_skipped_time_entry(issue: dict[str, Any], reason: str) -> None:
    print(f"skipped time entry #{issue.get('id')}: {reason}")
