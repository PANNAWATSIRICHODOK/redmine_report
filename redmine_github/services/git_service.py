from __future__ import annotations

import subprocess

from redmine_github.models import Commit


def read_commits(repo: str, since: str = "", until: str = "", limit: int = 0) -> list[Commit]:
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

    output = subprocess.check_output(command, text=True).strip("\x1e\n")
    commits: list[Commit] = []
    for record in output.split("\x1e"):
        if not record.strip():
            continue
        short_sha, sha, date, subject, body = (record.strip("\n").split("\x1f", 4) + [""])[:5]
        commits.append(Commit(short_sha, sha, date, subject.strip(), body.strip()))
    return commits
