from contextlib import redirect_stdout
from io import StringIO

from redmine_github.controllers.import_controller import (
    ImportOptions,
    draft_from_commit,
    estimate_ai_hours,
    estimate_hours,
    estimate_spent_hours,
)
from redmine_github.models import Commit
from redmine_github.views.cli_view import print_skipped_existing
from redmine_github.views.cli_view import print_skipped_time_entry


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
    assert draft.note == "Body text"
    assert draft.assigned_to_id == 28
    assert draft.status_id == 5
    assert draft.done_ratio == 100
    assert draft.estimated_hours == 2.5
    assert draft.spent_hours == 1.0
    assert draft.ai_score == 1.0
    assert "AI Score: 1 hours (35%)" in draft.description
    assert draft.custom_fields == [{"id": 12, "value": "1"}]


def test_estimate_spent_hours_stays_below_estimate() -> None:
    assert estimate_ai_hours(1.0, 50) is None
    assert estimate_ai_hours(2.0, 25) == 1.0
    assert estimate_ai_hours(2.5, 50) == 1.0
    assert estimate_ai_hours(4.0, 50) == 2.0
    assert estimate_spent_hours(1.0, None) == 1.0
    assert estimate_spent_hours(2.0, 1.0) == 1.0
    assert estimate_spent_hours(2.5, 1.0) == 1.5
    assert estimate_spent_hours(4.0, 2.0) == 2.0


def test_estimate_hours_keyword_range() -> None:
    assert estimate_hours(Commit("", "", "", "docs typo", "")) == 0.5
    assert estimate_hours(Commit("", "", "", "init", "")) == 1.0
    assert estimate_hours(Commit("", "", "", "fix bug", "")) == 2.5
    assert estimate_hours(Commit("", "", "", "feature report api", "")) == 4.0
    assert estimate_hours(Commit("", "", "", "refactor integration workflow", "")) == 8.0
    assert estimate_hours(Commit("", "", "", "architecture migration multi-day", "")) == 18.0


def test_ai_score_is_omitted_when_it_cannot_be_below_estimate() -> None:
    draft = draft_from_commit(
        Commit("abc1234", "abc123456789", "2026-06-22", "Tiny task", ""),
        ImportOptions(".", "", "", 0, "", 17, 3, None, None, None, 1.0, None, 9, 12, "[git] ", False),
    )
    assert draft.estimated_hours == 1.0
    assert draft.ai_score is None
    assert draft.custom_fields is None
    assert "AI Score: omitted" in draft.description


def test_skip_message() -> None:
    draft = draft_from_commit(
        Commit("abc1234", "abc123456789", "2026-06-22", "Add thing", ""),
        ImportOptions(".", "", "", 0, "", 17, 3, None, None, None, None, None, None, None, "[git] ", False),
    )
    output = StringIO()
    with redirect_stdout(output):
        print_skipped_existing({"id": 123}, draft)
    assert output.getvalue().strip() == "skipped existing #123: [git] Add thing"

    output = StringIO()
    with redirect_stdout(output):
        print_skipped_time_entry({"id": 123}, "hours below Redmine minimum 0.5")
    assert output.getvalue().strip() == "skipped time entry #123: hours below Redmine minimum 0.5"


if __name__ == "__main__":
    test_issue_fields()
    test_estimate_spent_hours_stays_below_estimate()
    test_estimate_hours_keyword_range()
    test_ai_score_is_omitted_when_it_cannot_be_below_estimate()
    test_skip_message()
    print("ok")
