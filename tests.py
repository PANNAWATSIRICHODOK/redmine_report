from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO

from redmine_github.importer import (
    Commit,
    ImportOptions,
    IssueDraft,
    draft_from_commit,
    draft_summary,
    estimate_ai_hours,
    estimate_hours,
    estimate_spent_hours,
    print_created,
)
from redmine_github.redmine import RedmineClient


class FakeResponse:
    def json(self) -> dict:
        return {"issue": {"id": 123}}


class FakeRedmineClient(RedmineClient):
    def __init__(self) -> None:
        self.payloads = []

    def _post(self, path, payload, error_prefix):
        self.payloads.append(deepcopy(payload))
        if len(self.payloads) == 1:
            raise RuntimeError("Redmine create issue failed: Ai score ไม่อยู่ในรายการ")
        return FakeResponse()


def test_issue_fields() -> None:
    draft = draft_from_commit(
        Commit(
            short_sha="abc1234",
            sha="abc123456789",
            date="2026-06-22",
            subject="Fix Redmine sync",
            body="Body text",
            files_changed=4,
            lines_changed=80,
            paths=("redmine_github/config.py",),
        ),
        ImportOptions(
            repo=".",
            since="",
            until="",
            limit=0,
            author="Developer",
            project_id=17,
            tracker_id=3,
            parent_issue_id=4184,
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
    assert draft.note == "Body text"
    assert draft.parent_issue_id == 4184
    assert draft.assigned_to_id == 28
    assert draft.status_id == 5
    assert draft.done_ratio == 100
    assert draft.estimated_hours == 2.5
    assert draft.spent_hours == 1.0
    assert draft.ai_score == 1.0
    assert "AI Score: 1 hours (35%)" in draft.description
    assert draft.custom_fields == [{"id": 12, "value": "1"}]
    assert draft_summary(draft) == "estimated=2.5h ai=1h spent=1h"


def test_estimate_spent_hours_stays_below_estimate() -> None:
    assert estimate_ai_hours(1.0, 50) is None
    assert estimate_ai_hours(2.0, 25) == 1.0
    assert estimate_ai_hours(2.5, 50) == 1.0
    assert estimate_ai_hours(4.0, 50) == 2.0
    assert estimate_spent_hours(1.0, None) == 0.5
    assert estimate_spent_hours(2.0, 1.0) == 0.5
    assert estimate_spent_hours(2.5, 1.0) == 1.0
    assert estimate_spent_hours(4.0, 2.0) == 1.5


def test_estimate_hours_keyword_range() -> None:
    assert estimate_hours(Commit("", "", "", "docs typo", "")) == 2.0
    assert estimate_hours(Commit("", "", "", "init", "")) == 4.0
    assert estimate_hours(Commit("", "", "", "fix bug", "")) == 6.0
    assert estimate_hours(Commit("", "", "", "feature report api", "")) == 10.0
    assert estimate_hours(Commit("", "", "", "refactor integration workflow", "")) == 16.0
    assert estimate_hours(Commit("", "", "", "architecture migration multi-day", "")) == 24.0
    assert estimate_hours(Commit("", "", "", "fix bug", "", 4, 80, ("app/config.py",))) == 12.0
    assert estimate_hours(Commit("", "", "", "feature", "body", 9, 450, ("auth/login.py",))) == 36.0
    assert estimate_hours(Commit("", "", "", "architecture migration multi-day", "", 20, 1000, ("db/migration.sql",))) == 48.0
    assert estimate_hours(Commit("", "", "", "architecture migration multi-day", "body", 20, 2000, ("auth/db/migration.sql",))) == 50.0


def test_ai_score_is_omitted_when_it_cannot_be_below_estimate() -> None:
    draft = draft_from_commit(
        Commit("abc1234", "abc123456789", "2026-06-22", "Tiny task", ""),
        ImportOptions(".", "", "", 0, "", 17, 3, None, None, None, None, 1.0, None, 9, 12, "[git] ", False),
    )
    assert draft.estimated_hours == 1.0
    assert draft.ai_score is None
    assert draft.custom_fields is None
    assert "AI Score: omitted" in draft.description


def test_skip_message() -> None:
    draft = draft_from_commit(
        Commit("abc1234", "abc123456789", "2026-06-22", "Add thing", ""),
        ImportOptions(".", "", "", 0, "", 17, 3, None, None, None, None, None, None, None, None, "[git] ", False),
    )
    output = StringIO()
    with redirect_stdout(output):
        print_created("skipped existing", {"id": 123}, draft)
    assert output.getvalue().strip() == "skipped existing #123: [git] Add thing (estimated=6h ai=2h spent=3.5h)"

    output = StringIO()
    with redirect_stdout(output):
        print("skipped time entry #123: hours below Redmine minimum 0.5")
    assert output.getvalue().strip() == "skipped time entry #123: hours below Redmine minimum 0.5"


def test_create_issue_retries_without_invalid_ai_score() -> None:
    redmine = FakeRedmineClient()
    issue = redmine.create_issue(
        16,
        IssueDraft("subject", "description", custom_fields=[{"id": 14, "value": "99"}]),
        3,
    )
    assert issue["id"] == 123
    assert redmine.payloads[0]["issue"]["custom_fields"] == [{"id": 14, "value": "99"}]
    assert "custom_fields" not in redmine.payloads[1]["issue"]


if __name__ == "__main__":
    test_issue_fields()
    test_estimate_spent_hours_stays_below_estimate()
    test_estimate_hours_keyword_range()
    test_ai_score_is_omitted_when_it_cannot_be_below_estimate()
    test_skip_message()
    test_create_issue_retries_without_invalid_ai_score()
    print("ok")
