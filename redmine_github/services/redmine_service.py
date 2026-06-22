from __future__ import annotations

from typing import Any

import requests

from redmine_github.config import REQUEST_TIMEOUT, RedmineConfig
from redmine_github.models import IssueDraft


class RedmineService:
    def __init__(self, config: RedmineConfig) -> None:
        self.base_url = config.base_url
        self.verify_ssl = config.verify_ssl
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "X-Redmine-API-Key": config.api_key,
            }
        )

    def create_issue(
        self,
        project_id: int,
        draft: IssueDraft,
        tracker_id: int | None = None,
    ) -> dict[str, Any]:
        issue: dict[str, Any] = {
            "project_id": project_id,
            "subject": draft.subject,
            "description": draft.description,
        }
        if tracker_id:
            issue["tracker_id"] = tracker_id
        if draft.assigned_to_id:
            issue["assigned_to_id"] = draft.assigned_to_id
        if draft.status_id:
            issue["status_id"] = draft.status_id
        if draft.done_ratio is not None:
            issue["done_ratio"] = draft.done_ratio
        if draft.estimated_hours:
            issue["estimated_hours"] = draft.estimated_hours
        if draft.custom_fields:
            issue["custom_fields"] = draft.custom_fields

        response = self._post("/issues.json", {"issue": issue}, "Redmine create issue failed")

        data = response.json()
        created_issue = data.get("issue")
        if not isinstance(created_issue, dict):
            raise RuntimeError("Redmine response did not include issue details")
        return created_issue

    def create_time_entry(
        self,
        issue_id: int,
        hours: float,
        activity_id: int,
        spent_on: str,
        comments: str,
    ) -> dict[str, Any]:
        response = self._post(
            "/time_entries.json",
            {
                "time_entry": {
                    "issue_id": issue_id,
                    "hours": hours,
                    "activity_id": activity_id,
                    "spent_on": spent_on,
                    "comments": comments,
                }
            },
            "Redmine create time entry failed",
        )
        data = response.json()
        time_entry = data.get("time_entry")
        if not isinstance(time_entry, dict):
            raise RuntimeError("Redmine response did not include time entry details")
        return time_entry

    def update_issue(
        self,
        issue_id: int,
        status_id: int | None = None,
        done_ratio: int | None = None,
    ) -> None:
        issue: dict[str, Any] = {}
        if status_id:
            issue["status_id"] = status_id
        if done_ratio is not None:
            issue["done_ratio"] = done_ratio
        if not issue:
            return
        self._put(f"/issues/{issue_id}.json", {"issue": issue}, "Redmine update issue failed")

    def find_issue_by_commit(self, project_id: int, commit_sha: str) -> dict[str, Any] | None:
        data = self._get_json(
            "/issues.json",
            {
                "project_id": project_id,
                "status_id": "*",
                "limit": 25,
                "description": f"~{commit_sha}",
            },
            "Redmine search issue failed",
        )
        issues = data.get("issues", [])
        if not isinstance(issues, list):
            return None
        marker = f"Git commit: {commit_sha}"
        for issue in issues:
            if isinstance(issue, dict) and marker in str(issue.get("description", "")):
                return issue
        return None

    def current_user_id(self) -> int:
        data = self._get("/users/current.json", "Redmine current user failed").json()
        user = data.get("user")
        if not isinstance(user, dict) or not user.get("id"):
            raise RuntimeError("Redmine response did not include current user id")
        return int(user["id"])

    def closed_status_id(self) -> int:
        data = self._get("/issue_statuses.json", "Redmine issue statuses failed").json()
        statuses = data.get("issue_statuses", [])
        for status in statuses:
            if isinstance(status, dict) and str(status.get("name", "")).casefold() == "closed":
                return int(status["id"])
        raise RuntimeError("Redmine does not expose a Closed status")

    def _get_json(self, path: str, params: dict[str, Any], error_prefix: str) -> dict[str, Any]:
        try:
            response = self.session.get(
                f"{self.base_url}{path}",
                params=params,
                timeout=REQUEST_TIMEOUT,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            message = str(exc)
            response = getattr(exc, "response", None)
            if response is not None and response.text.strip():
                message = f"{message}: {response.text.strip()[:300]}"
            raise RuntimeError(f"{error_prefix}: {message}") from exc

    def _get(self, path: str, error_prefix: str) -> requests.Response:
        try:
            response = self.session.get(
                f"{self.base_url}{path}",
                timeout=REQUEST_TIMEOUT,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            message = str(exc)
            response = getattr(exc, "response", None)
            if response is not None and response.text.strip():
                message = f"{message}: {response.text.strip()[:300]}"
            raise RuntimeError(f"{error_prefix}: {message}") from exc

    def _post(self, path: str, payload: dict[str, Any], error_prefix: str) -> requests.Response:
        try:
            response = self.session.post(
                f"{self.base_url}{path}",
                json=payload,
                timeout=REQUEST_TIMEOUT,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            message = str(exc)
            response = getattr(exc, "response", None)
            if response is not None and response.text.strip():
                message = f"{message}: {response.text.strip()[:300]}"
            raise RuntimeError(f"{error_prefix}: {message}") from exc

    def _put(self, path: str, payload: dict[str, Any], error_prefix: str) -> requests.Response:
        try:
            response = self.session.put(
                f"{self.base_url}{path}",
                json=payload,
                timeout=REQUEST_TIMEOUT,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            message = str(exc)
            response = getattr(exc, "response", None)
            if response is not None and response.text.strip():
                message = f"{message}: {response.text.strip()[:300]}"
            raise RuntimeError(f"{error_prefix}: {message}") from exc
