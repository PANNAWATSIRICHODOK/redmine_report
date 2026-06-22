from __future__ import annotations

from typing import Any

from redmine_github.models import IssueDraft


def print_no_commits() -> None:
    print("No commits found.")


def print_dry_run(draft: IssueDraft) -> None:
    print(f"DRY RUN: {draft.subject}")


def print_created(issue: dict[str, Any], draft: IssueDraft) -> None:
    print(f"created #{issue.get('id')}: {draft.subject}")


def print_skipped_existing(issue: dict[str, Any], draft: IssueDraft) -> None:
    print(f"skipped existing #{issue.get('id')}: {draft.subject}")


def print_skipped_time_entry(issue: dict[str, Any], reason: str) -> None:
    print(f"skipped time entry #{issue.get('id')}: {reason}")
