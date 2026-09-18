from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO

from redmine_github.importer import (
    Commit,
    ImportOptions,
    IssueDraft,
    ensure_minimum_spent_by_commit_day,
    draft_from_commit,
    draft_summary,
    estimate_ai_hours,
    estimate_hours,
    estimate_spent_hours,
    print_created,
)
from redmine_github.redmine import RedmineClient
from automation import scheduled_date
import redmine_github.importer as importer_module


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
    assert draft_summary(draft) == "estimated=2.5h (0.31 mandays) ai=1h spent=1h"


def test_estimate_spent_hours_stays_below_estimate() -> None:
    assert estimate_ai_hours(1.0, 50) is None
    assert estimate_ai_hours(2.0, 25) == 1.0
    assert estimate_ai_hours(2.5, 50) == 1.0
    assert estimate_ai_hours(4.0, 50) == 2.0
    assert estimate_spent_hours(1.0) == 0.5
    assert estimate_spent_hours(2.0) == 0.5
    assert estimate_spent_hours(2.5) == 1.0
    assert estimate_spent_hours(4.0) == 2.5


def test_spent_hours_meet_daily_manday_minimum() -> None:
    commits = [
        Commit("a", "a", "2026-06-21", "A", ""),
        Commit("b", "b", "2026-06-21", "B", ""),
        Commit("c", "c", "2026-06-22", "C", ""),
    ]
    allocated = ensure_minimum_spent_by_commit_day(commits, [10.0, 10.0, 20.0])
    assert allocated == [10.0, 10.0, 20.0]
    assert sum(allocated) == 40.0
    assert ensure_minimum_spent_by_commit_day(commits[:2], [1.0, 1.0]) == [4.0, 4.0]
    assert ensure_minimum_spent_by_commit_day([Commit("d", "d", "2026-06-23", "D", "")], [0.5]) == [8.0]


def test_commit_gaps_weight_one_daily_manday() -> None:
    commits = [
        Commit("a", "a", "2026-06-21", "A", "", timestamp="2026-06-21T09:00:00+07:00"),
        Commit("b", "b", "2026-06-21", "B", "", timestamp="2026-06-21T10:00:00+07:00"),
        Commit("c", "c", "2026-06-21", "C", "", timestamp="2026-06-21T15:00:00+07:00"),
    ]
    allocated = ensure_minimum_spent_by_commit_day(commits, [1.0, 1.0, 6.0])
    assert allocated == [2.0, 3.0, 3.0]
    assert sum(allocated) == 8.0


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


def test_low_estimate_still_meets_time_buffer() -> None:
    draft = draft_from_commit(
        Commit("abc1234", "abc123456789", "2026-06-22", "Tiny task", ""),
        ImportOptions(".", "", "", 0, "", 17, 3, None, None, None, None, 1.0, None, 9, 12, "[git] ", False),
    )
    assert draft.estimated_hours == 2.0
    assert draft.spent_hours == 0.5
    assert draft.ai_score == 1.0
    assert draft.custom_fields == [{"id": 12, "value": "1"}]


def test_standalone_feature_has_no_parent() -> None:
    draft = draft_from_commit(
        Commit("abc1234", "abc123456789", "2026-06-22", "[standalone] Add export", ""),
        ImportOptions(".", "", "", 0, "", 17, 3, 4184, None, None, None, None, None, 9, 12, "[git] ", False, 2),
    )
    assert draft.subject == "[git] Add export"
    assert draft.parent_issue_id is None
    assert draft.tracker_id == 2

    unmarked = draft_from_commit(
        Commit("def5678", "def567890123", "2026-06-22", "Add dashboard", ""),
        ImportOptions(".", "", "", 0, "", 17, 3, 4184, None, None, None, None, None, 9, 12, "[git] ", False, 2, True),
    )
    assert unmarked.parent_issue_id is None
    assert unmarked.tracker_id == 2


def test_skip_message() -> None:
    draft = draft_from_commit(
        Commit("abc1234", "abc123456789", "2026-06-22", "Add thing", ""),
        ImportOptions(".", "", "", 0, "", 17, 3, None, None, None, None, None, None, None, None, "[git] ", False),
    )
    output = StringIO()
    with redirect_stdout(output):
        print_created("skipped existing", {"id": 123}, draft)
    assert output.getvalue().strip() == "skipped existing #123: [git] Add thing (estimated=6h (0.75 mandays) ai=2h spent=4.5h)"

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


def test_scheduled_date_moves_weekends_to_friday() -> None:
    assert scheduled_date(2026, 8).isoformat() == "2026-08-28"
    assert scheduled_date(2026, 11).isoformat() == "2026-11-27"
    assert scheduled_date(2027, 2).isoformat() == "2027-02-26"


def test_post_defaults_reach_created_draft() -> None:
    class FakeImportRedmine:
        draft = None

        def __init__(self, _config): pass
        def current_user_id(self): return 28
        def closed_status_id(self): return 5
        def find_issue_by_commit(self, _project_id, _sha): return None
        def create_issue(self, _project_id, draft, _tracker_id):
            FakeImportRedmine.draft = draft
            return {"id": 123}
        def create_time_entry(self, **_kwargs): pass
        def update_issue(self, *_args, **_kwargs): pass

    original_client = importer_module.RedmineClient
    original_config = importer_module.load_redmine_config
    original_commits = importer_module.read_commits
    try:
        importer_module.RedmineClient = FakeImportRedmine
        importer_module.load_redmine_config = lambda: object()
        importer_module.read_commits = lambda *_args, **_kwargs: [Commit("a", "a", "2026-01-01", "Feature", "")]
        with redirect_stdout(StringIO()):
            importer_module.import_issues(
                ImportOptions(".", "", "", 0, "", 17, 2, None, None, None, 100, None, None, 9, None, "[git] ", True, 2, True)
            )
    finally:
        importer_module.RedmineClient = original_client
        importer_module.load_redmine_config = original_config
        importer_module.read_commits = original_commits
    assert FakeImportRedmine.draft.assigned_to_id == 28
    assert FakeImportRedmine.draft.status_id == 5


if __name__ == "__main__":
    test_issue_fields()
    test_estimate_spent_hours_stays_below_estimate()
    test_spent_hours_meet_daily_manday_minimum()
    test_commit_gaps_weight_one_daily_manday()
    test_estimate_hours_keyword_range()
    test_low_estimate_still_meets_time_buffer()
    test_standalone_feature_has_no_parent()
    test_skip_message()
    test_create_issue_retries_without_invalid_ai_score()
    test_scheduled_date_moves_weekends_to_friday()
    test_post_defaults_reach_created_draft()
    print("ok")
