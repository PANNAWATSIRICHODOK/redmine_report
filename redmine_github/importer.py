from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

from redmine_github.redmine import ConfigError, RedmineClient, load_redmine_config

ESTIMATED_HOURS_MULTIPLIER = 2.0


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
    parent_issue_id: int | None = None
    assigned_to_id: int | None = None
    status_id: int | None = None
    done_ratio: int | None = None
    estimated_hours: float | None = None
    spent_hours: float | None = None
    ai_score: float | None = None
    custom_fields: list[dict[str, object]] | None = None


@dataclass(frozen=True)
class ImportOptions:
    repo: str
    since: str
    until: str
    limit: int
    author: str
    project_id: int
    tracker_id: int | None
    parent_issue_id: int | None
    assigned_to_id: int | None
    status_id: int | None
    done_ratio: int | None
    estimated_hours: float | None
    spent_hours: float | None
    activity_id: int | None
    ai_score_field_id: int | None
    prefix: str
    post: bool


def commit_stats(repo: str, sha: str) -> tuple[int, int, tuple[str, ...]]:
    output = subprocess.check_output(["git", "-C", repo, "show", "--numstat", "--format=", sha], text=True)
    paths: list[str] = []
    lines_changed = 0
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, deleted, path = parts[0], parts[1], parts[2]
        paths.append(path)
        if added.isdigit():
            lines_changed += int(added)
        if deleted.isdigit():
            lines_changed += int(deleted)
    return len(paths), lines_changed, tuple(paths)


def read_commits(repo: str, since: str = "", until: str = "", limit: int = 0, author: str = "") -> list[Commit]:
    command = [
        "git",
        "-C",
        repo,
        "log",
        "--reverse",
        "--date=short",
        "--pretty=format:%h%x1f%H%x1f%ad%x1f%s%x1f%b%x1e",
    ]
    if limit:
        command.insert(4, f"-n{limit}")
    if since:
        command.append(f"--since={since}")
    if until:
        command.append(f"--until={until}")
    if author:
        command.append(f"--author={author}")

    output = subprocess.check_output(command, text=True).strip("\x1e\n")
    commits: list[Commit] = []
    for record in output.split("\x1e"):
        if not record.strip():
            continue
        short_sha, sha, date, subject, body = (record.strip("\n").split("\x1f", 4) + [""])[:5]
        files_changed, lines_changed, paths = commit_stats(repo, sha)
        commits.append(Commit(short_sha, sha, date, subject.strip(), body.strip(), files_changed, lines_changed, paths))
    return commits


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
    return f"estimated={estimated}h ai={ai if ai == '-' else ai + 'h'} spent={spent}h"


def estimate_hours(commit: Commit) -> float:
    text = f"{commit.subject} {commit.body}".casefold()
    if any(word in text for word in ["docs", "typo", "comment", "format", "readme"]):
        hours = 1.0
    elif any(word in text for word in ["architecture", "migration", "enterprise", "multi-day"]):
        hours = 12.0
    elif any(word in text for word in ["integration", "workflow", "refactor", "migrate"]):
        hours = 8.0
    elif any(word in text for word in ["feature", "report", "dashboard", "api"]):
        hours = 5.0
    elif any(word in text for word in ["fix", "bug", "add", "support"]):
        hours = 3.0
    else:
        hours = 2.0

    if commit.files_changed > 8:
        hours += 3.0
    elif commit.files_changed > 3:
        hours += 1.0

    if commit.lines_changed > 400:
        hours += 6.0
    elif commit.lines_changed > 150:
        hours += 3.0
    elif commit.lines_changed > 50:
        hours += 1.0

    if commit.body:
        hours += 1.0

    changed_paths = " ".join(commit.paths).casefold()
    if any(word in changed_paths for word in ["docker", "config", ".env", "settings"]):
        hours += 1.0
    if any(word in changed_paths for word in ["auth", "payment", "database", "db/", "migration"]):
        hours += 3.0

    return hours * ESTIMATED_HOURS_MULTIPLIER


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
    buffer_hours = max(0.5, round(estimated_hours * 0.1 * 4) / 4)
    available_hours = estimated_hours - (ai_hours or 0) - buffer_hours
    return max(0.0, round(available_hours, 2))


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
            for part in [f"Git commit: {commit.sha}", f"Commit date: {commit.date}", ai_score_line, "", commit.body]
            if part
        ),
        note=commit.body,
        parent_issue_id=options.parent_issue_id,
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


def print_created(prefix: str, issue: dict[str, Any], draft: IssueDraft) -> None:
    print(f"{prefix} #{issue.get('id')}: {draft.subject} ({draft_summary(draft)})")


def import_issues(options: ImportOptions) -> int:
    if not options.project_id:
        raise ConfigError("Missing --project-id or REDMINE_PROJECT_ID")
    if options.spent_hours and not options.activity_id:
        raise ConfigError("Missing --activity-id or REDMINE_ACTIVITY_ID for spent time")

    commits = read_commits(options.repo, options.since, options.until, options.limit, options.author)
    if not commits:
        print("No commits found.")
        return 0

    redmine = None
    if options.post:
        redmine = RedmineClient(load_redmine_config())
        if options.assigned_to_id is None:
            options = ImportOptions(**{**options.__dict__, "assigned_to_id": redmine.current_user_id()})
        if options.status_id is None:
            options = ImportOptions(**{**options.__dict__, "status_id": redmine.closed_status_id()})

    for commit in commits:
        draft = draft_from_commit(commit, options)
        if not options.post:
            print(f"DRY RUN: {draft.subject} ({draft_summary(draft)})")
            continue

        assert redmine is not None
        existing_issue = redmine.find_issue_by_commit(options.project_id, commit.sha)
        if existing_issue:
            print_created("skipped existing", existing_issue, draft)
            continue

        issue = redmine.create_issue(options.project_id, draft, options.tracker_id)
        if draft.spent_hours and options.activity_id:
            if draft.spent_hours < 0.5:
                print(f"skipped time entry #{issue.get('id')}: hours below Redmine minimum 0.5")
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
                    print(f"skipped time entry #{issue.get('id')}: {exc}")
        redmine.update_issue(int(issue["id"]), status_id=draft.status_id, done_ratio=draft.done_ratio, notes=draft.note)
        print_created("created", issue, draft)
    return 0
