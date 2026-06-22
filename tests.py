from redmine_github.controllers.import_controller import ImportOptions, draft_from_commit
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
        ImportOptions(
            repo=".",
            since="",
            until="",
            limit=0,
            author="Developer",
            project_id=17,
            tracker_id=3,
            assigned_to_id=28,
            status_id=5,
            done_ratio=100,
            estimated_hours=2.5,
            spent_hours=1.0,
            activity_id=9,
            ai_score_field_id=12,
            prefix="[git] ",
            post=False,
        ),
    )
    assert draft.subject == "[git] Fix Redmine sync"
    assert "Git commit: abc123456789" in draft.description
    assert "Commit date: 2026-06-22" in draft.description
    assert "Body text" in draft.description
    assert draft.assigned_to_id == 28
    assert draft.status_id == 5
    assert draft.done_ratio == 100
    assert draft.estimated_hours == 2.5
    assert draft.custom_fields == [{"id": 12, "value": "2"}]


if __name__ == "__main__":
    test_issue_fields()
    print("ok")
