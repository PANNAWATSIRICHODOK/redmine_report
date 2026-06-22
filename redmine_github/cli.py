from __future__ import annotations

import argparse
import subprocess
import sys

from .config import ConfigError, env_float, env_int, env_str, load_dotenv
from .controllers.import_controller import ImportOptions, import_issues


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an integer: {value}") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {value}") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def parser() -> argparse.ArgumentParser:
    load_dotenv()
    cli = argparse.ArgumentParser(description="Create Redmine issues from git commits.")
    cli.add_argument("--repo", default=".", help="git repo path")
    cli.add_argument("--since", default="", help="git log --since value, e.g. 2026-06-01")
    cli.add_argument("--until", default="", help="git log --until value, e.g. 2026-06-22")
    cli.add_argument("--author", default=env_str("GIT_AUTHOR"), help="git log --author value")
    cli.add_argument("--limit", type=int, default=0, help="max commits to read")
    cli.add_argument("--project-id", type=positive_int, default=env_int("REDMINE_PROJECT_ID"))
    cli.add_argument("--tracker-id", type=positive_int, default=env_int("REDMINE_TRACKER_ID") or None)
    cli.add_argument("--assigned-to-id", type=positive_int, default=env_int("REDMINE_ASSIGNED_TO_ID") or None)
    cli.add_argument("--status-id", type=positive_int, default=env_int("REDMINE_STATUS_ID") or None)
    cli.add_argument("--done-ratio", type=int, default=env_int("REDMINE_DONE_RATIO", -1))
    cli.add_argument("--estimated-hours", type=positive_float, default=env_float("REDMINE_ESTIMATED_HOURS"))
    cli.add_argument("--spent-hours", type=positive_float, default=env_float("REDMINE_SPENT_HOURS"))
    cli.add_argument("--activity-id", type=positive_int, default=env_int("REDMINE_ACTIVITY_ID") or None)
    cli.add_argument("--ai-score-field-id", type=positive_int, default=env_int("REDMINE_AI_SCORE_FIELD_ID") or None)
    cli.add_argument("--prefix", default=env_str("REDMINE_ISSUE_PREFIX", "[git] "), help="issue subject prefix")
    cli.add_argument("--post", action="store_true", help="actually create issues; default is dry-run")
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    prefix = args.prefix if args.prefix.endswith(" ") else f"{args.prefix} "
    return import_issues(
        ImportOptions(
            repo=args.repo,
            since=args.since,
            until=args.until,
            limit=args.limit,
            author=args.author,
            project_id=args.project_id,
            tracker_id=args.tracker_id,
            assigned_to_id=args.assigned_to_id,
            status_id=args.status_id,
            done_ratio=args.done_ratio if args.done_ratio >= 0 else None,
            estimated_hours=args.estimated_hours,
            spent_hours=args.spent_hours,
            activity_id=args.activity_id,
            ai_score_field_id=args.ai_score_field_id,
            prefix=prefix,
            post=args.post,
        )
    )


def run() -> None:
    try:
        raise SystemExit(main())
    except (ConfigError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
