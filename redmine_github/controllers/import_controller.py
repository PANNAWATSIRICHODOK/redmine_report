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
    print_skipped_time_entry,
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
    if any(word in text for word in ["docs", "typo", "comment", "format", "readme"]):
        hours = 0.5
    elif any(word in text for word in ["architecture", "migration", "enterprise", "multi-day"]):
        hours = 8.0
    elif any(word in text for word in ["integration", "workflow", "refactor", "migrate"]):
        hours = 5.0
    elif any(word in text for word in ["feature", "report", "dashboard", "api"]):
        hours = 3.0
    elif any(word in text for word in ["fix", "bug", "add", "support"]):
        hours = 1.5
    else:
        hours = 1.0

    if commit.files_changed > 8:
        hours += 1.5
    elif commit.files_changed > 3:
        hours += 0.5

    if commit.lines_changed > 400:
        hours += 3.0
    elif commit.lines_changed > 150:
        hours += 1.5
    elif commit.lines_changed > 50:
        hours += 0.5

    if commit.body:
        hours += 0.5

    changed_paths = " ".join(commit.paths).casefold()
    if any(word in changed_paths for word in ["docker", "config", ".env", "settings"]):
        hours += 0.5
    if any(word in changed_paths for word in ["auth", "payment", "database", "db/", "migration"]):
        hours += 2.0

    return hours


def score_commit(commit: Commit) -> int:
    text = f"{commit.subject} {commit.body}".casefold()
    score = 25
    if any(word in text for word in ["feature", "refactor", "integration", "api"]):
        score += 10
    if commit.body or len(commit.subject) > 40:
        score += 10
    if any(word in text for word in ["security", "payment", "migration", "production"]):
        score += 5
    return min(score, 50)


def format_hours(value: float) -> str:
    rounded = round(value, 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def estimate_ai_hours(estimated_hours: float, ai_percent: int) -> float | None:
    if estimated_hours <= 1:
        return None
    raw_hours = estimated_hours * ai_percent / 100
    rounded_hours = round(raw_hours)
    if rounded_hours >= estimated_hours:
        rounded_hours = int(estimated_hours) - 1
    ai_hours = float(max(1, rounded_hours))
    return ai_hours if ai_hours < estimated_hours else None


def estimate_spent_hours(estimated_hours: float, ai_hours: float | None) -> float:
    if ai_hours is None:
        return estimated_hours
    return max(0.25, round(estimated_hours - ai_hours, 2))


def draft_from_commit(commit: Commit, options: ImportOptions) -> IssueDraft:
    ai_percent = score_commit(commit)
    estimated_hours = options.estimated_hours or estimate_hours(commit)
    ai_hours = estimate_ai_hours(estimated_hours, ai_percent)
    spent_hours = options.spent_hours or estimate_spent_hours(estimated_hours, ai_hours)
    ai_score_line = (
        f"AI Score: {format_hours(ai_hours)} hours ({ai_percent}%)"
        if ai_hours is not None
        else "AI Score: omitted because estimated hours is too low"
    )
    return IssueDraft(
        subject=f"{options.prefix}{commit.subject}"[:255],
        description="\n".join(
            part
            for part in [
                f"Git commit: {commit.sha}",
                f"Commit date: {commit.date}",
                ai_score_line,
                "",
                commit.body,
            ]
            if part
        ),
        note=commit.body,
        assigned_to_id=options.assigned_to_id,
        status_id=options.status_id,
        done_ratio=100 if options.done_ratio is None else options.done_ratio,
        estimated_hours=estimated_hours,
        spent_hours=spent_hours,
        ai_score=ai_hours,
        custom_fields=(
            [{"id": options.ai_score_field_id, "value": format_hours(ai_hours)}]
            if options.ai_score_field_id and ai_hours is not None
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
            notes=draft.note,
        )
        if draft.spent_hours and options.activity_id:
            if draft.spent_hours < 0.5:
                print_skipped_time_entry(issue, "hours below Redmine minimum 0.5")
            else:
                try:
                    redmine.create_time_entry(
                        issue_id=int(issue["id"]),
                        hours=draft.spent_hours,
                        activity_id=options.activity_id,
                        spent_on=commit.date,
                        comments=draft.subject,
                    )
                except RuntimeError as exc:
                    print_skipped_time_entry(issue, str(exc))
        print_created(issue, draft)
    return 0
