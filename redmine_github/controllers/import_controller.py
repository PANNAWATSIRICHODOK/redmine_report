from __future__ import annotations

from dataclasses import dataclass

from redmine_github.config import ConfigError, load_redmine_config
from redmine_github.models import Commit, IssueDraft
from redmine_github.services.git_service import read_commits
from redmine_github.views.cli_view import print_created, print_dry_run, print_no_commits


@dataclass(frozen=True)
class ImportOptions:
    repo: str
    since: str
    until: str
    limit: int
    project_id: int
    tracker_id: int | None
    prefix: str
    post: bool


def draft_from_commit(commit: Commit, prefix: str) -> IssueDraft:
    return IssueDraft(
        subject=f"{prefix}{commit.subject}"[:255],
        description="\n".join(
            part
            for part in [
                f"Git commit: {commit.sha}",
                f"Commit date: {commit.date}",
                "",
                commit.body,
            ]
            if part
        ),
    )


def import_issues(options: ImportOptions) -> int:
    if not options.project_id:
        raise ConfigError("Missing --project-id or REDMINE_PROJECT_ID")

    commits = read_commits(options.repo, options.since, options.until, options.limit)
    if not commits:
        print_no_commits()
        return 0

    redmine = None
    if options.post:
        from redmine_github.services.redmine_service import RedmineService

        redmine = RedmineService(load_redmine_config())
    for commit in commits:
        draft = draft_from_commit(commit, options.prefix)
        if not options.post:
            print_dry_run(draft)
            continue
        assert redmine is not None
        issue = redmine.create_issue(options.project_id, draft, options.tracker_id)
        print_created(issue, draft)
    return 0
