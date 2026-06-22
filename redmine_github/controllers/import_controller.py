from __future__ import annotations

from dataclasses import dataclass

from redmine_github.config import ConfigError, load_redmine_config
from redmine_github.models import Commit, IssueDraft
from redmine_github.services.git_service import read_commits
from redmine_github.views.cli_view import (
    print_created,
    print_dry_run,
    print_no_commits,
    print_skipped_existing,
)


@dataclass(frozen=True)
class ImportOptions:
    repo: str
    since: str
    until: str
    limit: int
    author: str
    project_id: int
    tracker_id: int | None
    assigned_to_id: int | None
    status_id: int | None
    done_ratio: int | None
    estimated_hours: float | None
    spent_hours: float | None
    activity_id: int | None
    ai_score_field_id: int | None
    prefix: str
    post: bool


def estimate_hours(commit: Commit) -> float:
    text = f"{commit.subject} {commit.body}".casefold()
    if any(word in text for word in ["refactor", "migrate", "integration", "workflow"]):
        return 2.5
    if any(word in text for word in ["fix", "bug", "report", "feature", "add"]):
        return 1.0
    return 0.5


def score_commit(commit: Commit) -> int:
    text = f"{commit.subject} {commit.body}".casefold()
    score = 1
    if any(word in text for word in ["feature", "refactor", "integration", "api"]):
        score += 1
    if commit.body or len(commit.subject) > 40:
        score += 1
    if any(word in text for word in ["security", "payment", "migration", "production"]):
        score += 1
    return min(score, 5)


def draft_from_commit(commit: Commit, options: ImportOptions) -> IssueDraft:
    ai_score = score_commit(commit)
    return IssueDraft(
        subject=f"{options.prefix}{commit.subject}"[:255],
        description="\n".join(
            part
            for part in [
                f"Git commit: {commit.sha}",
                f"Commit date: {commit.date}",
                f"AI Score: {ai_score}",
                "",
                commit.body,
            ]
            if part
        ),
        assigned_to_id=options.assigned_to_id,
        status_id=options.status_id,
        done_ratio=100 if options.done_ratio is None else options.done_ratio,
        estimated_hours=options.estimated_hours or estimate_hours(commit),
        custom_fields=(
            [{"id": options.ai_score_field_id, "value": str(ai_score)}]
            if options.ai_score_field_id
            else None
        ),
    )


def import_issues(options: ImportOptions) -> int:
    if not options.project_id:
        raise ConfigError("Missing --project-id or REDMINE_PROJECT_ID")
    if options.spent_hours and not options.activity_id:
        raise ConfigError("Missing --activity-id or REDMINE_ACTIVITY_ID for spent time")

    commits = read_commits(options.repo, options.since, options.until, options.limit, options.author)
    if not commits:
        print_no_commits()
        return 0

    redmine = None
    if options.post:
        from redmine_github.services.redmine_service import RedmineService

        redmine = RedmineService(load_redmine_config())
        if options.assigned_to_id is None:
            options = ImportOptions(**{**options.__dict__, "assigned_to_id": redmine.current_user_id()})
        if options.status_id is None:
            options = ImportOptions(**{**options.__dict__, "status_id": redmine.closed_status_id()})
    for commit in commits:
        draft = draft_from_commit(commit, options)
        if not options.post:
            print_dry_run(draft)
            continue
        assert redmine is not None
        existing_issue = redmine.find_issue_by_commit(options.project_id, commit.sha)
        if existing_issue:
            print_skipped_existing(existing_issue, draft)
            continue
        issue = redmine.create_issue(options.project_id, draft, options.tracker_id)
        redmine.update_issue(
            issue_id=int(issue["id"]),
            status_id=draft.status_id,
            done_ratio=draft.done_ratio,
        )
        if options.spent_hours and options.activity_id:
            redmine.create_time_entry(
                issue_id=int(issue["id"]),
                hours=options.spent_hours,
                activity_id=options.activity_id,
                spent_on=commit.date,
                comments=draft.subject,
            )
        print_created(issue, draft)
    return 0
