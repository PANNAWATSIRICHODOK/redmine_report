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

        try:
            response = self.session.post(
                f"{self.base_url}/issues.json",
                json={"issue": issue},
                timeout=REQUEST_TIMEOUT,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            message = str(exc)
            response = getattr(exc, "response", None)
            if response is not None and response.text.strip():
                message = f"{message}: {response.text.strip()[:300]}"
            raise RuntimeError(f"Redmine create issue failed: {message}") from exc

        data = response.json()
        created_issue = data.get("issue")
        if not isinstance(created_issue, dict):
            raise RuntimeError("Redmine response did not include issue details")
        return created_issue
