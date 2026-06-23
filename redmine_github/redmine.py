from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

REQUEST_TIMEOUT = 30
BASE_DIR = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class RedmineConfig:
    base_url: str
    api_key: str
    verify_ssl: bool


def load_dotenv(path: Path = BASE_DIR / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def env_int(name: str, default: int = 0) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def env_float(name: str, default: float | None = None) -> float | None:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def load_redmine_config() -> RedmineConfig:
    load_dotenv()
    base_url = os.getenv("REDMINE_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("REDMINE_API_KEY", "").strip()
    if not base_url or not api_key:
        raise ConfigError("Missing REDMINE_BASE_URL or REDMINE_API_KEY")
    return RedmineConfig(base_url, api_key, env_flag("REDMINE_VERIFY_SSL", True))


class RedmineClient:
    def __init__(self, config: RedmineConfig) -> None:
        self.base_url = config.base_url
        self.verify_ssl = config.verify_ssl
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "X-Redmine-API-Key": config.api_key})

    def create_issue(self, project_id: int, draft: Any, tracker_id: int | None = None) -> dict[str, Any]:
        issue: dict[str, Any] = {"project_id": project_id, "subject": draft.subject, "description": draft.description}
        optional_fields = {
            "tracker_id": tracker_id,
            "parent_issue_id": draft.parent_issue_id,
            "assigned_to_id": draft.assigned_to_id,
            "status_id": draft.status_id,
            "done_ratio": draft.done_ratio,
            "estimated_hours": draft.estimated_hours,
            "custom_fields": draft.custom_fields,
        }
        issue.update({key: value for key, value in optional_fields.items() if value is not None})

        try:
            response = self._post("/issues.json", {"issue": issue}, "Redmine create issue failed")
        except RuntimeError as exc:
            if "Ai score" not in str(exc) or not issue.pop("custom_fields", None):
                raise
            response = self._post("/issues.json", {"issue": issue}, "Redmine create issue failed")

        created_issue = response.json().get("issue")
        if not isinstance(created_issue, dict):
            raise RuntimeError("Redmine response did not include issue details")
        return created_issue

    def create_time_entry(self, issue_id: int, hours: float, activity_id: int, spent_on: str, comments: str) -> None:
        self._post(
            "/time_entries.json",
            {"time_entry": {"issue_id": issue_id, "hours": hours, "activity_id": activity_id, "spent_on": spent_on, "comments": comments}},
            "Redmine create time entry failed",
        )

    def update_issue(self, issue_id: int, status_id: int | None = None, done_ratio: int | None = None, notes: str = "") -> None:
        issue = {key: value for key, value in {"status_id": status_id, "done_ratio": done_ratio, "notes": notes}.items() if value not in (None, "")}
        if issue:
            self._put(f"/issues/{issue_id}.json", {"issue": issue}, "Redmine update issue failed")

    def find_issue_by_commit(self, project_id: int, commit_sha: str) -> dict[str, Any] | None:
        data = self._get_json(
            "/issues.json",
            {"project_id": project_id, "status_id": "*", "limit": 25, "description": f"~{commit_sha}"},
            "Redmine search issue failed",
        )
        marker = f"Git commit: {commit_sha}"
        for issue in data.get("issues", []):
            if isinstance(issue, dict) and marker in str(issue.get("description", "")):
                return issue
        return None

    def current_user_id(self) -> int:
        user = self._get("/users/current.json", "Redmine current user failed").json().get("user")
        if not isinstance(user, dict) or not user.get("id"):
            raise RuntimeError("Redmine response did not include current user id")
        return int(user["id"])

    def closed_status_id(self) -> int:
        statuses = self._get("/issue_statuses.json", "Redmine issue statuses failed").json().get("issue_statuses", [])
        for status in statuses:
            if isinstance(status, dict) and str(status.get("name", "")).casefold() == "closed":
                return int(status["id"])
        raise RuntimeError("Redmine does not expose a Closed status")

    def _get_json(self, path: str, params: dict[str, Any], error_prefix: str) -> dict[str, Any]:
        return self._get(path, error_prefix, params=params).json()

    def _get(self, path: str, error_prefix: str, params: dict[str, Any] | None = None) -> requests.Response:
        return self._request("get", path, error_prefix, params=params)

    def _post(self, path: str, payload: dict[str, Any], error_prefix: str) -> requests.Response:
        return self._request("post", path, error_prefix, json=payload)

    def _put(self, path: str, payload: dict[str, Any], error_prefix: str) -> requests.Response:
        return self._request("put", path, error_prefix, json=payload)

    def _request(self, method: str, path: str, error_prefix: str, **kwargs: Any) -> requests.Response:
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                timeout=REQUEST_TIMEOUT,
                verify=self.verify_ssl,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            message = str(exc)
            response = getattr(exc, "response", None)
            if response is not None and response.text.strip():
                message = f"{message}: {response.text.strip()[:300]}"
            raise RuntimeError(f"{error_prefix}: {message}") from exc
