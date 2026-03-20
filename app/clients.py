from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from .config import PAGE_LIMIT, REQUEST_TIMEOUT, SQL_TIMEOUT, RedmineConfig, SupersetConfig, env_int


class RedmineClient:
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

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self.session.get(
                f"{self.base_url}{path}",
                params=params,
                timeout=REQUEST_TIMEOUT,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            message = str(exc)
            response = getattr(exc, "response", None)
            if response is not None:
                body = response.text.strip()
                if body:
                    message = f"{message}: {body[:300]}"
            raise RuntimeError(f"Redmine request failed for {path}: {message}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"Redmine returned invalid JSON for {path}") from exc

    def get_current_user(self) -> dict[str, Any]:
        data = self._get_json("/users/current.json")
        user = data.get("user")
        if not isinstance(user, dict):
            raise RuntimeError("Redmine response did not include current user details")
        return user

    def get_user(self, user_id: int) -> dict[str, Any]:
        data = self._get_json(f"/users/{user_id}.json")
        user = data.get("user")
        if not isinstance(user, dict):
            raise RuntimeError(f"Redmine response did not include details for user {user_id}")
        return user

    def list_users(self, status: int = 1) -> list[dict[str, Any]]:
        return self._collect_paginated_items(
            path="/users.json",
            base_params={"status": status},
            item_key="users",
            error_message="Redmine response did not include a users list",
        )

    def list_time_entries(
        self,
        user_id: int,
        spent_from: Any = None,
        spent_to: Any = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "user_id": user_id,
            "sort": "spent_on:desc",
        }
        if spent_from:
            params["from"] = spent_from.isoformat()
        if spent_to:
            params["to"] = spent_to.isoformat()

        return self._collect_paginated_items(
            path="/time_entries.json",
            base_params=params,
            item_key="time_entries",
            error_message="Redmine response did not include a time_entries list",
        )

    def list_assigned_issues(self, user_id: int) -> list[dict[str, Any]]:
        return self._collect_paginated_items(
            path="/issues.json",
            base_params={
                "assigned_to_id": user_id,
                "status_id": "*",
            },
            item_key="issues",
            error_message="Redmine response did not include an issues list",
        )

    def _collect_paginated_items(
        self,
        path: str,
        base_params: dict[str, Any],
        item_key: str,
        error_message: str,
    ) -> list[dict[str, Any]]:
        first_page = self._get_json(
            path,
            params={
                **base_params,
                "limit": PAGE_LIMIT,
                "offset": 0,
            },
        )
        first_batch = first_page.get(item_key, [])
        if not isinstance(first_batch, list):
            raise RuntimeError(error_message)

        total_count = int(first_page.get("total_count", len(first_batch)))
        if total_count <= PAGE_LIMIT or not first_batch:
            return [item for item in first_batch if isinstance(item, dict)]

        offsets = list(range(PAGE_LIMIT, total_count, PAGE_LIMIT))
        batches_by_offset: dict[int, list[dict[str, Any]]] = {
            0: [item for item in first_batch if isinstance(item, dict)]
        }

        def fetch_offset(offset: int) -> tuple[int, list[dict[str, Any]]]:
            data = self._get_json(
                path,
                params={
                    **base_params,
                    "limit": PAGE_LIMIT,
                    "offset": offset,
                },
            )
            batch = data.get(item_key, [])
            if not isinstance(batch, list):
                raise RuntimeError(error_message)
            return offset, [item for item in batch if isinstance(item, dict)]

        worker_count = min(env_int("REDMINE_PAGE_WORKERS", 6, minimum=1), len(offsets))
        if worker_count == 1 or len(offsets) == 1:
            for offset in offsets:
                resolved_offset, batch = fetch_offset(offset)
                batches_by_offset[resolved_offset] = batch
        else:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_map = {
                    executor.submit(fetch_offset, offset): offset
                    for offset in offsets
                }
                for future in as_completed(future_map):
                    resolved_offset, batch = future.result()
                    batches_by_offset[resolved_offset] = batch

        items: list[dict[str, Any]] = []
        for offset in sorted(batches_by_offset):
            items.extend(batches_by_offset[offset])
        return items

    def _fetch_issue(self, issue_id: int) -> dict[str, Any] | None:
        try:
            response = self.session.get(
                f"{self.base_url}/issues/{issue_id}.json",
                timeout=REQUEST_TIMEOUT,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
        except requests.RequestException:
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        issue = payload.get("issue")
        return issue if isinstance(issue, dict) else None

    def _fetch_issue_batch(self, issue_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not issue_ids:
            return {}

        data = self._get_json(
            "/issues.json",
            params={
                "issue_id": ",".join(map(str, issue_ids)),
                "status_id": "*",
                "limit": len(issue_ids),
            },
        )
        issues = data.get("issues", [])
        if not isinstance(issues, list):
            raise RuntimeError("Redmine response did not include an issues list")

        return {
            int(issue["id"]): issue
            for issue in issues
            if isinstance(issue, dict) and issue.get("id")
        }

    def get_issues(self, issue_ids: set[int]) -> dict[int, dict[str, Any]]:
        if not issue_ids:
            return {}

        sorted_issue_ids = sorted(issue_ids)
        batch_size = env_int("REDMINE_ISSUE_BATCH_SIZE", 100, minimum=1)
        worker_count = min(env_int("REDMINE_ISSUE_WORKERS", 8, minimum=1), len(sorted_issue_ids))
        chunks = [sorted_issue_ids[index : index + batch_size] for index in range(0, len(sorted_issue_ids), batch_size)]
        fetched_results: dict[int, dict[str, Any] | None] = {}

        def fetch_chunk(chunk: list[int]) -> dict[int, dict[str, Any] | None]:
            try:
                chunk_results = self._fetch_issue_batch(chunk)
            except Exception:
                chunk_results = {}

            if len(chunk_results) == len(chunk):
                return chunk_results

            for issue_id in chunk:
                chunk_results.setdefault(issue_id, self._fetch_issue(issue_id))
            return chunk_results

        if len(chunks) == 1 or worker_count == 1:
            for chunk in chunks:
                fetched_results.update(fetch_chunk(chunk))
        else:
            max_workers = min(worker_count, len(chunks))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {executor.submit(fetch_chunk, chunk): chunk for chunk in chunks}
                for future in as_completed(future_map):
                    try:
                        fetched_results.update(future.result())
                    except Exception:
                        for issue_id in future_map[future]:
                            fetched_results[issue_id] = self._fetch_issue(issue_id)

        return {
            issue_id: issue
            for issue_id, issue in sorted(fetched_results.items())
            if isinstance(issue, dict)
        }


class SupersetClient:
    def __init__(self, config: SupersetConfig) -> None:
        self.base_url = config.base_url
        self.username = config.username
        self.password = config.password
        self.provider = config.provider
        self.database_id = config.database_id
        self.schema = config.schema
        self.verify_ssl = config.verify_ssl
        self.session = requests.Session()
        self.access_token = ""

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        authenticated: bool = False,
        timeout: int = REQUEST_TIMEOUT,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.login()}"

        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                json=payload,
                headers=headers,
                timeout=timeout,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            message = str(exc)
            response = getattr(exc, "response", None)
            if response is not None:
                body = response.text.strip()
                if body:
                    message = f"{message}: {body[:300]}"
            if isinstance(exc, requests.exceptions.SSLError):
                message = f"{message}. Set SUPERSET_VERIFY_SSL=false if this Superset uses a private certificate."
            raise RuntimeError(f"Superset request failed for {path}: {message}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"Superset returned invalid JSON for {path}") from exc

    def login(self) -> str:
        if self.access_token:
            return self.access_token

        data = self._request_json(
            "POST",
            "/api/v1/security/login",
            payload={
                "username": self.username,
                "password": self.password,
                "provider": self.provider,
                "refresh": True,
            },
        )
        access_token = str(data.get("access_token", "")).strip()
        if not access_token:
            raise RuntimeError("Superset login response did not include an access token")
        self.access_token = access_token
        return access_token

    def execute_sql(self, sql: str) -> list[dict[str, Any]]:
        data = self._request_json(
            "POST",
            "/api/v1/sqllab/execute/",
            payload={
                "database_id": self.database_id,
                "schema": self.schema,
                "sql": sql,
            },
            authenticated=True,
            timeout=SQL_TIMEOUT,
        )
        rows = data.get("data")
        if not isinstance(rows, list):
            raise RuntimeError("Superset SQL response did not include row data")
        return [row for row in rows if isinstance(row, dict)]
