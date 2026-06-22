from __future__ import annotations

import subprocess

from redmine_github.models import Commit


def commit_stats(repo: str, sha: str) -> tuple[int, int, tuple[str, ...]]:
    output = subprocess.check_output(
        ["git", "-C", repo, "show", "--numstat", "--format=", sha],
        text=True,
    )
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


def read_commits(
    repo: str,
    since: str = "",
    until: str = "",
    limit: int = 0,
    author: str = "",
) -> list[Commit]:
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
