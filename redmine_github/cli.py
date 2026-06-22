from __future__ import annotations

import argparse
import subprocess
import sys

from .config import ConfigError, env_int, load_dotenv
from .controllers.import_controller import ImportOptions, import_issues


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an integer: {value}") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def parser() -> argparse.ArgumentParser:
    load_dotenv()
    cli = argparse.ArgumentParser(description="Create Redmine issues from git commits.")
    cli.add_argument("--repo", default=".", help="git repo path")
    cli.add_argument("--since", default="", help="git log --since value, e.g. 2026-06-01")
    cli.add_argument("--until", default="", help="git log --until value, e.g. 2026-06-22")
    cli.add_argument("--limit", type=int, default=0, help="max commits to read")
    cli.add_argument("--project-id", type=positive_int, default=env_int("REDMINE_PROJECT_ID"))
    cli.add_argument("--tracker-id", type=positive_int, default=env_int("REDMINE_TRACKER_ID") or None)
    cli.add_argument("--prefix", default="[git] ", help="issue subject prefix")
    cli.add_argument("--post", action="store_true", help="actually create issues; default is dry-run")
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return import_issues(
        ImportOptions(
            repo=args.repo,
            since=args.since,
            until=args.until,
            limit=args.limit,
            project_id=args.project_id,
            tracker_id=args.tracker_id,
            prefix=args.prefix,
            post=args.post,
        )
    )


def run() -> None:
    try:
        raise SystemExit(main())
    except (ConfigError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
