from __future__ import annotations

import argparse
import calendar
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from redmine_github.importer import ImportOptions, import_issues
from redmine_github.redmine import RedmineClient, env_int, env_str, load_dotenv, load_redmine_config

BASE_DIR = Path(__file__).resolve().parent
TIMEZONE = ZoneInfo("Asia/Bangkok")


def notify(message: str) -> None:
    escaped = message.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(
        ["/usr/bin/osascript", "-e", f'display notification "{escaped}" with title "Git → Redmine"'],
        check=False,
    )


def scheduled_date(year: int, month: int) -> date:
    day = date(year, month, 28)
    offset = 1 if day.weekday() == calendar.SATURDAY else 2 if day.weekday() == calendar.SUNDAY else 0
    return day.replace(day=28 - offset)


def repositories(root: Path) -> list[Path]:
    found: list[Path] = []
    for current, dirs, _ in os.walk(root):
        dirs[:] = [name for name in dirs if name not in {".venv", "node_modules"} and not name.startswith(".")]
        if (Path(current) / ".git").exists():
            if Path(current).resolve() != BASE_DIR:
                found.append(Path(current))
            dirs.clear()
    return sorted(found)


def git_remote(repo: Path) -> str:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repo), "remote", "get-url", "origin"],
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def normalized_remote(remote: str) -> str:
    return remote.casefold().removesuffix(".git").rstrip("/")


def project_for_repo(repo: Path, remote: str, projects: list[dict], configured_repo: Path | None, configured_id: int) -> dict | None:
    if configured_repo and repo.resolve() == configured_repo.resolve() and configured_id:
        return next((project for project in projects if int(project.get("id", 0)) == configured_id), {"id": configured_id})
    normalized = normalized_remote(remote)
    if normalized:
        match = next((project for project in projects if normalized in str(project.get("description", "")).casefold()), None)
        if match:
            return match
    name = repo.name.casefold()
    return next(
        (project for project in projects if str(project.get("name", "")).casefold() == name or str(project.get("identifier", "")).casefold() == name),
        None,
    )


def unique_identifier(name: str, projects: list[dict]) -> str:
    base = re.sub(r"[^a-z0-9-]+", "-", name.casefold()).strip("-") or "git-project"
    used = {str(project.get("identifier", "")) for project in projects}
    identifier = base
    suffix = 2
    while identifier in used:
        identifier = f"{base}-{suffix}"
        suffix += 1
    return identifier


def options(repo: Path, project_id: int, standalone: bool, post: bool, limit: int) -> ImportOptions:
    prefix = env_str("REDMINE_ISSUE_PREFIX", "[git] ")
    return ImportOptions(
        repo=str(repo),
        since=env_str("GIT_SINCE"),
        until=env_str("GIT_UNTIL"),
        limit=limit,
        author=env_str("GIT_AUTHOR"),
        project_id=project_id,
        tracker_id=env_int("REDMINE_TRACKER_ID") or None,
        parent_issue_id=None if standalone else env_int("REDMINE_PARENT_ISSUE_ID") or None,
        assigned_to_id=env_int("REDMINE_ASSIGNED_TO_ID") or None,
        status_id=env_int("REDMINE_STATUS_ID") or None,
        done_ratio=env_int("REDMINE_DONE_RATIO", 100),
        estimated_hours=None,
        spent_hours=None,
        activity_id=env_int("REDMINE_ACTIVITY_ID") or None,
        ai_score_field_id=env_int("REDMINE_AI_SCORE_FIELD_ID") or None,
        prefix=prefix if prefix.endswith(" ") else f"{prefix} ",
        post=post,
        feature_tracker_id=env_int("REDMINE_FEATURE_TRACKER_ID", 2),
        standalone=standalone,
    )


def run(post: bool, force: bool, limit: int) -> int:
    load_dotenv()
    now = datetime.now(TIMEZONE)
    if not force and now.date() != scheduled_date(now.year, now.month):
        return 0

    print(f"[{now.isoformat(timespec='seconds')}] START Git → Redmine", flush=True)
    notify("เริ่มตรวจสอบ commit และเพิ่มข้อมูลลง Redmine")
    subprocess.run([sys.executable, str(BASE_DIR / "tests.py")], cwd=BASE_DIR, check=True)

    root = Path(env_str("GIT_SCAN_ROOT", str(BASE_DIR.parent))).expanduser()
    configured_path = env_str("GIT_REPO_PATH")
    configured_repo = Path(configured_path).expanduser() if configured_path else None
    configured_project_id = env_int("REDMINE_PROJECT_ID")
    feature_tracker_id = env_int("REDMINE_FEATURE_TRACKER_ID", 2)
    redmine = RedmineClient(load_redmine_config())
    projects = redmine.projects()
    failures: list[str] = []
    processed = 0

    for repo in repositories(root):
        remote = git_remote(repo)
        project = project_for_repo(repo, remote, projects, configured_repo, configured_project_id)
        standalone = not project or int(project.get("id", 0)) != configured_project_id
        try:
            project_id = int(project["id"]) if project else 1
            print(f"repository {repo.name} -> {'project #' + str(project_id) if project else 'NEW project'}", flush=True)
            import_issues(options(repo, project_id, standalone, False, limit))
            if post and not project:
                project = redmine.create_project(
                    repo.name,
                    unique_identifier(repo.name, projects),
                    f"Git remote: {remote}" if remote else f"Git repository: {repo}",
                    feature_tracker_id,
                )
                projects.append(project)
                project_id = int(project["id"])
                print(f"created project #{project_id}: {repo.name}")
            if post:
                import_issues(options(repo, project_id, standalone, True, limit))
            processed += 1
        except Exception as exc:  # keep other repositories running
            failures.append(f"{repo.name}: {exc}")
            print(f"ERROR {failures[-1]}", file=sys.stderr, flush=True)

    if failures:
        raise RuntimeError("; ".join(failures))
    mode = "POST" if post else "DRY RUN"
    print(f"[{datetime.now(TIMEZONE).isoformat(timespec='seconds')}] DONE {mode}: {processed} repositories", flush=True)
    notify(f"เสร็จสิ้น: ตรวจสอบ {processed} repositories")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Scheduled Git → Redmine automation")
    parser.add_argument("--post", action="store_true", help="write projects, issues and time entries")
    parser.add_argument("--force", action="store_true", help="run outside the scheduled date")
    parser.add_argument("--limit", type=int, default=0, help="limit commits per repository for testing")
    args = parser.parse_args()
    try:
        raise SystemExit(run(args.post, args.force, args.limit))
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr, flush=True)
        notify(f"ทำงานไม่สำเร็จ: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
