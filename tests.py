from redmine_github.controllers.import_controller import draft_from_commit
from redmine_github.models import Commit


def test_issue_fields() -> None:
    draft = draft_from_commit(
        Commit(
            short_sha="abc1234",
            sha="abc123456789",
            date="2026-06-22",
            subject="Fix Redmine sync",
            body="Body text",
        ),
        "[git] ",
    )
    assert draft.subject == "[git] Fix Redmine sync"
    assert "Git commit: abc123456789" in draft.description
    assert "Commit date: 2026-06-22" in draft.description
    assert "Body text" in draft.description


if __name__ == "__main__":
    test_issue_fields()
    print("ok")
