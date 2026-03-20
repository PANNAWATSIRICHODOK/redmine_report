from __future__ import annotations

import csv
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from threading import Lock
from time import monotonic
from typing import Any

from .clients import RedmineClient, SupersetClient
from .config import (
    COMPANY_FIELD_NAME,
    CUSTOMER_FIELD_NAME,
    DEFAULT_SUPERSET_DIRECTORY_SQL,
    UNKNOWN_REQUESTER,
    UNMATCHED_DEPARTMENT,
    USER_ALIASES_PATH,
    load_redmine_config,
    load_superset_config,
)

DIRECTORY_CACHE_TTL_SECONDS = 300
_DIRECTORY_CACHE_LOCK = Lock()
_DIRECTORY_CACHE: dict[str, Any] = {
    "expires_at": 0.0,
    "value": None,
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\ufeff", "").split())


def dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_text(value)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def round_hours(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def format_hours(value: float) -> str:
    rounded = round_hours(value)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def timestamp_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def build_range_label(spent_from: date | None, spent_to: date | None) -> str:
    if spent_from and spent_to:
        return f"{spent_from.isoformat()} ถึง {spent_to.isoformat()}"
    if spent_from:
        return f"ตั้งแต่ {spent_from.isoformat()}"
    if spent_to:
        return f"ถึง {spent_to.isoformat()}"
    return "ทั้งหมด"


def list_to_label(values: list[str]) -> str:
    return ", ".join(values)


def display_name(user: dict[str, Any]) -> str:
    full_name = " ".join(
        part for part in [normalize_text(user.get("firstname")), normalize_text(user.get("lastname"))] if part
    )
    return full_name or normalize_text(user.get("login")) or "Unknown user"


def serialize_redmine_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(user.get("id") or 0),
        "name": display_name(user),
        "login": normalize_text(user.get("login")),
        "admin": bool(user.get("admin")),
    }


def resolve_report_user_ids(query: dict[str, list[str]], default_user_id: int) -> list[int]:
    raw_values = query.get("user_id", [])
    if not raw_values:
        return [default_user_id]

    user_ids: list[int] = []
    seen: set[int] = set()
    for raw_value in raw_values:
        normalized_value = normalize_text(raw_value)
        if not normalized_value:
            continue

        for part in normalized_value.replace(",", " ").split():
            try:
                user_id = int(part)
            except ValueError as exc:
                raise ValueError("User filter must be a numeric Redmine user id") from exc

            if user_id <= 0:
                raise ValueError("User filter must be greater than zero")
            if user_id in seen:
                continue

            seen.add(user_id)
            user_ids.append(user_id)

    return user_ids or [default_user_id]


def build_directory_profile_aliases(row: dict[str, Any]) -> list[str]:
    return dedupe_strings(
        [
            normalize_text(row.get("full_name_th")),
            normalize_text(row.get("full_name_en")),
            " ".join(
                part
                for part in [normalize_text(row.get("firstname")), normalize_text(row.get("lastname"))]
                if part
            ),
            " ".join(
                part
                for part in [normalize_text(row.get("firstname_th")), normalize_text(row.get("lastname_th"))]
                if part
            ),
            normalize_text(row.get("username")),
            normalize_text(row.get("username_ad")),
            normalize_text(row.get("email")),
            normalize_text(row.get("user_code")),
            normalize_text(row.get("sap_user")),
        ]
    )


def build_user_directory_from_superset_rows(rows: list[dict[str, Any]], source_label: str) -> dict[str, Any]:
    lookup: dict[str, dict[str, str]] = {}
    departments: set[str] = set()
    unique_people: set[str] = set()

    for row in rows:
        department_name = normalize_text(row.get("department_name"))
        if department_name:
            departments.add(department_name)

        full_name_th = normalize_text(row.get("full_name_th"))
        full_name_en = normalize_text(row.get("full_name_en"))
        display_name = (
            full_name_th
            or full_name_en
            or normalize_text(row.get("username"))
            or normalize_text(row.get("id"))
        )
        person_key = normalize_text(row.get("id")) or normalize_text(row.get("email")) or display_name.casefold()
        unique_people.add(person_key.casefold())

        profile = {
            "name": display_name,
            "primary_department": department_name,
        }
        for alias in build_directory_profile_aliases(row):
            lookup.setdefault(alias.casefold(), profile)

    return {
        "exists": True,
        "source_label": source_label,
        "lookup": lookup,
        "total_users": len(unique_people),
        "unique_departments": len(departments),
    }


def load_user_directory(client: SupersetClient) -> dict[str, Any]:
    try:
        rows = client.execute_sql(DEFAULT_SUPERSET_DIRECTORY_SQL)
    except Exception as exc:
        raise RuntimeError(f"Superset sync failed: {exc}") from exc

    return build_user_directory_from_superset_rows(rows=rows, source_label="Superset E-Office : MySQL")


def load_user_directory_cached(client: SupersetClient) -> dict[str, Any]:
    now = monotonic()
    with _DIRECTORY_CACHE_LOCK:
        cached_value = _DIRECTORY_CACHE["value"]
        if isinstance(cached_value, dict) and now < float(_DIRECTORY_CACHE["expires_at"]):
            return cached_value

    directory = load_user_directory(client)
    with _DIRECTORY_CACHE_LOCK:
        _DIRECTORY_CACHE["value"] = directory
        _DIRECTORY_CACHE["expires_at"] = monotonic() + DIRECTORY_CACHE_TTL_SECONDS
    return directory


def _get_row_value(row: dict[str, Any], columns: tuple[str, ...]) -> str:
    for column in columns:
        value = normalize_text(row.get(column))
        if value:
            return value
    return ""


def load_user_aliases() -> dict[str, Any]:
    if not USER_ALIASES_PATH.exists():
        return {
            "exists": False,
            "mappings": {},
            "count": 0,
        }

    mappings: dict[str, str] = {}
    with USER_ALIASES_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source_name = _get_row_value(row, ("redmine_name", "source_name", "alias", "display_name"))
            target_name = _get_row_value(
                row,
                ("directory_name", "target_name", "mapped_name", "csv_name", "u_name"),
            )
            if source_name and target_name:
                mappings[source_name.casefold()] = target_name

    return {
        "exists": True,
        "mappings": mappings,
        "count": len(mappings),
    }


def match_directory_person(name: str, user_directory: dict[str, Any], user_aliases: dict[str, Any]) -> dict[str, Any]:
    normalized_name = normalize_text(name)
    if not normalized_name:
        return {
            "input_name": "",
            "matched": False,
            "match_type": "unmatched",
            "directory_name": "",
            "department": "",
        }

    alias_target = user_aliases["mappings"].get(normalized_name.casefold())
    lookup_name = normalize_text(alias_target or normalized_name)
    profile = user_directory["lookup"].get(lookup_name.casefold())
    if not isinstance(profile, dict):
        return {
            "input_name": normalized_name,
            "matched": False,
            "match_type": "unmatched",
            "directory_name": "",
            "department": "",
        }

    return {
        "input_name": normalized_name,
        "matched": True,
        "match_type": "alias" if alias_target else "exact",
        "directory_name": profile["name"],
        "department": profile["primary_department"],
    }


def serialize_entries(issue_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "date": entry["date"],
            "hours": round_hours(entry["hours"]),
            "hours_label": entry["hours_label"],
            "project": entry["project"],
            "activity": entry["activity"],
            "issue_id": entry["issue_id"],
            "issue_url": entry["issue_url"],
            "comments": entry["comments"],
            "user_id": int(((entry.get("user") or {}).get("id")) or 0),
            "user_name": normalize_text((entry.get("user") or {}).get("name")),
        }
        for entry in issue_entries
    ]


def summarize_entries(entries: list[dict[str, Any]], base_url: str) -> dict[str, Any]:
    total_hours = 0.0
    sortable_entries: list[tuple[tuple[str, int], dict[str, Any]]] = []
    unique_projects: set[str] = set()
    unique_activities: set[str] = set()

    for raw_entry in entries:
        spent_on = normalize_text(raw_entry.get("spent_on"))
        if not spent_on:
            continue

        try:
            hours = float(raw_entry.get("hours", 0) or 0)
        except (TypeError, ValueError):
            hours = 0.0

        issue_id = (raw_entry.get("issue") or {}).get("id")
        entry_id = int(raw_entry.get("id") or 0)
        project_name = normalize_text((raw_entry.get("project") or {}).get("name")) or "No project"
        activity_name = normalize_text((raw_entry.get("activity") or {}).get("name")) or "No activity"
        total_hours += hours
        unique_projects.add(project_name)
        unique_activities.add(activity_name)

        sortable_entries.append(
            (
                (spent_on, entry_id),
                {
                    "date": spent_on,
                    "hours": hours,
                    "hours_label": format_hours(hours),
                    "project": project_name,
                    "activity": activity_name,
                    "issue_id": issue_id,
                    "issue_url": f"{base_url}/issues/{issue_id}" if issue_id else "",
                    "comments": normalize_text(raw_entry.get("comments")),
                },
            )
        )

    sortable_entries.sort(key=lambda item: item[0], reverse=True)
    issue_entries = [entry for _, entry in sortable_entries]

    return {
        "summary": {
            "total_hours": round_hours(total_hours),
            "total_hours_label": format_hours(total_hours),
            "total_entries": len(issue_entries),
            "unique_project_count": len(unique_projects),
            "unique_activity_count": len(unique_activities),
        },
        "entries": serialize_entries(issue_entries),
        "issue_entries": issue_entries,
    }


def extract_custom_field_values(issue: dict[str, Any], field_name: str) -> list[str]:
    for field in issue.get("custom_fields") or []:
        if normalize_text((field or {}).get("name")) != field_name:
            continue

        raw_value = (field or {}).get("value")
        if isinstance(raw_value, list):
            return dedupe_strings([normalize_text(item) for item in raw_value])
        if raw_value is None:
            return []
        return dedupe_strings([normalize_text(raw_value)])
    return []


def build_issue_context(
    issue_id: int,
    issue: dict[str, Any] | None,
    fallback_project: str,
    user_directory: dict[str, Any],
    user_aliases: dict[str, Any],
    base_url: str,
) -> dict[str, Any]:
    issue = issue or {}
    customer_names = extract_custom_field_values(issue, CUSTOMER_FIELD_NAME)
    company_names = extract_custom_field_values(issue, COMPANY_FIELD_NAME)
    requester_candidates = customer_names or [normalize_text((issue.get("author") or {}).get("name"))]
    requester_candidates = [candidate for candidate in requester_candidates if candidate]

    requester_match = {
        "input_name": "",
        "matched": False,
        "match_type": "unmatched",
        "directory_name": "",
        "department": "",
    }
    for candidate in requester_candidates:
        requester_match = match_directory_person(candidate, user_directory, user_aliases)
        if requester_match["matched"]:
            break

    requester_name = requester_match["input_name"] or (
        requester_candidates[0] if requester_candidates else UNKNOWN_REQUESTER
    )
    department = requester_match["department"] if requester_match["matched"] else UNMATCHED_DEPARTMENT

    return {
        "issue_id": issue_id,
        "issue_url": f"{base_url}/issues/{issue_id}",
        "project": normalize_text((issue.get("project") or {}).get("name")) or fallback_project or "No project",
        "tracker_name": normalize_text((issue.get("tracker") or {}).get("name")) or "ไม่ระบุประเภทงาน",
        "subject": normalize_text(issue.get("subject")) or f"Issue #{issue_id}",
        "status": normalize_text((issue.get("status") or {}).get("name")),
        "priority": normalize_text((issue.get("priority") or {}).get("name")),
        "author_name": normalize_text((issue.get("author") or {}).get("name")),
        "assigned_to_name": normalize_text((issue.get("assigned_to") or {}).get("name")) or "ยังไม่ระบุผู้รับผิดชอบ",
        "company_names": company_names,
        "company_label": list_to_label(company_names),
        "requester_name": requester_name,
        "requester_source": "customer" if customer_names else "author",
        "requester_match_status": requester_match["match_type"],
        "department": department,
    }


def build_issue_insights(
    entries: list[dict[str, Any]],
    issue_details: dict[int, dict[str, Any] | None],
    user_directory: dict[str, Any],
    user_aliases: dict[str, Any],
    base_url: str,
) -> dict[str, Any]:
    issue_groups: dict[tuple[str, int], dict[str, Any]] = {}

    for entry in entries:
        issue_id = entry.get("issue_id")
        if not issue_id:
            continue

        year = normalize_text(entry.get("date"))[:4]
        if len(year) != 4 or not year.isdigit():
            continue

        context = build_issue_context(
            issue_id=int(issue_id),
            issue=issue_details.get(int(issue_id)),
            fallback_project=normalize_text(entry.get("project")),
            user_directory=user_directory,
            user_aliases=user_aliases,
            base_url=base_url,
        )

        group = issue_groups.setdefault(
            (year, int(issue_id)),
            {
                "year": year,
                "issue_id": int(issue_id),
                "issue_url": context["issue_url"],
                "project": context["project"],
                "tracker_name": context["tracker_name"],
                "subject": context["subject"],
                "status": context["status"],
                "priority": context["priority"],
                "author_name": context["author_name"],
                "assigned_to_name": context["assigned_to_name"],
                "company_names": context["company_names"],
                "company_label": context["company_label"],
                "requester_name": context["requester_name"],
                "requester_source": context["requester_source"],
                "requester_match_status": context["requester_match_status"],
                "department": context["department"],
                "hours": 0.0,
                "entries": 0,
                "first_spent_on": entry["date"],
                "last_spent_on": entry["date"],
            },
        )

        group["hours"] += float(entry["hours"])
        group["entries"] += 1
        group["first_spent_on"] = min(group["first_spent_on"], entry["date"])
        group["last_spent_on"] = max(group["last_spent_on"], entry["date"])

    yearly: dict[str, dict[str, Any]] = {}
    match_counts = Counter({"exact": 0, "alias": 0, "unmatched": 0})

    for record in issue_groups.values():
        record["hours"] = round_hours(record["hours"])
        record["hours_label"] = format_hours(record["hours"])

        year_data = yearly.setdefault(
            record["year"],
            {
                "total_hours": 0.0,
                "total_entries": 0,
                "issues": [],
                "departments": {},
                "requesters": {},
                "companies": {},
                "unmatched_requesters": {},
                "match_counts": Counter({"exact": 0, "alias": 0, "unmatched": 0}),
            },
        )

        year_data["total_hours"] += record["hours"]
        year_data["total_entries"] += record["entries"]
        year_data["issues"].append(record)
        year_data["match_counts"][record["requester_match_status"]] += 1
        match_counts[record["requester_match_status"]] += 1

        department_name = record["department"] or UNMATCHED_DEPARTMENT
        department_stats = year_data["departments"].setdefault(
            department_name,
            {"name": department_name, "hours": 0.0, "issues": 0},
        )
        department_stats["hours"] += record["hours"]
        department_stats["issues"] += 1

        requester_stats = year_data["requesters"].setdefault(
            record["requester_name"],
            {
                "name": record["requester_name"],
                "hours": 0.0,
                "issues": 0,
                "department": department_name,
                "match_status": record["requester_match_status"],
            },
        )
        requester_stats["hours"] += record["hours"]
        requester_stats["issues"] += 1

        for company_name in record["company_names"] or ["ไม่ระบุบริษัท"]:
            company_stats = year_data["companies"].setdefault(
                company_name,
                {"name": company_name, "hours": 0.0, "issues": 0},
            )
            company_stats["hours"] += record["hours"]
            company_stats["issues"] += 1

        if record["requester_match_status"] == "unmatched":
            unresolved = year_data["unmatched_requesters"].setdefault(
                record["requester_name"],
                {
                    "name": record["requester_name"],
                    "issues": 0,
                    "source": record["requester_source"],
                },
            )
            unresolved["issues"] += 1

    yearly_reports: list[dict[str, Any]] = []
    for year in sorted(yearly.keys(), reverse=True):
        year_data = yearly[year]
        sorted_issues = sorted(
            year_data["issues"],
            key=lambda item: (item["hours"], item["last_spent_on"], item["issue_id"]),
            reverse=True,
        )

        departments = [
            {
                "name": item["name"],
                "hours": round_hours(item["hours"]),
                "hours_label": format_hours(item["hours"]),
                "issues": item["issues"],
            }
            for item in sorted(
                year_data["departments"].values(),
                key=lambda item: (-item["hours"], item["name"].casefold()),
            )
        ]
        requesters = [
            {
                "name": item["name"],
                "hours": round_hours(item["hours"]),
                "hours_label": format_hours(item["hours"]),
                "issues": item["issues"],
                "department": item["department"],
                "match_status": item["match_status"],
            }
            for item in sorted(
                year_data["requesters"].values(),
                key=lambda item: (-item["hours"], item["name"].casefold()),
            )
        ]
        companies = [
            {
                "name": item["name"],
                "hours": round_hours(item["hours"]),
                "hours_label": format_hours(item["hours"]),
                "issues": item["issues"],
            }
            for item in sorted(
                year_data["companies"].values(),
                key=lambda item: (-item["hours"], item["name"].casefold()),
            )
        ]
        unmatched_requesters = [
            {
                "name": item["name"],
                "issues": item["issues"],
                "source": item["source"],
            }
            for item in sorted(
                year_data["unmatched_requesters"].values(),
                key=lambda item: (-item["issues"], item["name"].casefold()),
            )
        ]
        issues = [
            {
                "issue_id": item["issue_id"],
                "issue_url": item["issue_url"],
                "year": year,
                "project": item["project"],
                "tracker_name": item["tracker_name"],
                "subject": item["subject"],
                "status": item["status"],
                "priority": item["priority"],
                "author_name": item["author_name"],
                "assigned_to_name": item["assigned_to_name"],
                "company_label": item["company_label"],
                "requester_name": item["requester_name"],
                "requester_match_status": item["requester_match_status"],
                "hours": item["hours"],
                "hours_label": item["hours_label"],
                "entries": item["entries"],
                "first_spent_on": item["first_spent_on"],
                "last_spent_on": item["last_spent_on"],
                "department": item["department"],
            }
            for item in sorted_issues
        ]

        exact_count = year_data["match_counts"]["exact"]
        alias_count = year_data["match_counts"]["alias"]
        yearly_reports.append(
            {
                "year": year,
                "total_hours": round_hours(year_data["total_hours"]),
                "total_hours_label": format_hours(year_data["total_hours"]),
                "total_entries": year_data["total_entries"],
                "issue_count": len(issues),
                "matched_issue_count": exact_count + alias_count,
                "department_count": len([item for item in departments if item["name"] != UNMATCHED_DEPARTMENT]),
                "departments": departments,
                "requesters": requesters,
                "companies": companies,
                "issues": issues,
                "unmatched_requesters": unmatched_requesters,
                "match_breakdown": {
                    "exact": exact_count,
                    "alias": alias_count,
                    "unmatched": year_data["match_counts"]["unmatched"],
                },
            }
        )

    unique_departments = {
        normalize_text(record["department"])
        for record in issue_groups.values()
        if normalize_text(record["department"]) and normalize_text(record["department"]) != UNMATCHED_DEPARTMENT
    }
    unique_assignees = {
        normalize_text(record["assigned_to_name"])
        for record in issue_groups.values()
        if normalize_text(record["assigned_to_name"])
    }
    unique_trackers = {
        normalize_text(record["tracker_name"])
        for record in issue_groups.values()
        if normalize_text(record["tracker_name"])
    }

    return {
        "summary": {
            "unique_issue_count": len({record["issue_id"] for record in issue_groups.values()}),
            "years_covered": len(yearly_reports),
            "matched_issue_count": match_counts["exact"] + match_counts["alias"],
            "unique_department_count": len(unique_departments),
            "unique_assignee_count": len(unique_assignees),
            "unique_tracker_count": len(unique_trackers),
        },
        "yearly_reports": yearly_reports,
        "directory_summary": {
            "directory_loaded": user_directory["exists"],
            "directory_source_label": user_directory["source_label"],
            "total_users": user_directory["total_users"],
            "unique_departments": user_directory["unique_departments"],
            "alias_file_loaded": user_aliases["exists"],
            "alias_count": user_aliases["count"],
        },
    }


def build_directory_summary(user_directory: dict[str, Any], user_aliases: dict[str, Any]) -> dict[str, Any]:
    return {
        "directory_loaded": user_directory["exists"],
        "directory_source_label": user_directory["source_label"],
        "total_users": user_directory["total_users"],
        "unique_departments": user_directory["unique_departments"],
        "alias_file_loaded": user_aliases["exists"],
        "alias_count": user_aliases["count"],
    }


def build_assigned_issue_insights(
    issue_details: dict[int, dict[str, Any] | None],
    user_directory: dict[str, Any],
    user_aliases: dict[str, Any],
    base_url: str,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    match_counts = Counter({"exact": 0, "alias": 0, "unmatched": 0})

    for issue_id, issue in sorted(issue_details.items()):
        context = build_issue_context(
            issue_id=issue_id,
            issue=issue,
            fallback_project="",
            user_directory=user_directory,
            user_aliases=user_aliases,
            base_url=base_url,
        )
        match_counts[context["requester_match_status"]] += 1
        sort_updated_on = normalize_text((issue or {}).get("updated_on"))
        sort_created_on = normalize_text((issue or {}).get("created_on"))
        records.append(
            {
                "issue_id": issue_id,
                "issue_url": context["issue_url"],
                "year": "",
                "project": context["project"],
                "tracker_name": context["tracker_name"],
                "subject": context["subject"],
                "status": context["status"],
                "priority": context["priority"],
                "author_name": context["author_name"],
                "assigned_to_name": context["assigned_to_name"],
                "company_label": context["company_label"],
                "requester_name": context["requester_name"],
                "requester_match_status": context["requester_match_status"],
                "hours": 0.0,
                "hours_label": "0",
                "entries": 0,
                "first_spent_on": "",
                "last_spent_on": "",
                "department": context["department"],
                "sort_updated_on": sort_updated_on,
                "sort_created_on": sort_created_on,
            }
        )

    sorted_records = sorted(
        records,
        key=lambda item: (item["sort_updated_on"], item["sort_created_on"], item["issue_id"]),
        reverse=True,
    )
    issues = [
        {
            "issue_id": item["issue_id"],
            "issue_url": item["issue_url"],
            "year": item["year"],
            "project": item["project"],
            "tracker_name": item["tracker_name"],
            "subject": item["subject"],
            "status": item["status"],
            "priority": item["priority"],
            "author_name": item["author_name"],
            "assigned_to_name": item["assigned_to_name"],
            "company_label": item["company_label"],
            "requester_name": item["requester_name"],
            "requester_match_status": item["requester_match_status"],
            "hours": item["hours"],
            "hours_label": item["hours_label"],
            "entries": item["entries"],
            "first_spent_on": item["first_spent_on"],
            "last_spent_on": item["last_spent_on"],
            "department": item["department"],
        }
        for item in sorted_records
    ]

    unique_departments = {
        normalize_text(record["department"])
        for record in sorted_records
        if normalize_text(record["department"]) and normalize_text(record["department"]) != UNMATCHED_DEPARTMENT
    }
    unique_assignees = {
        normalize_text(record["assigned_to_name"])
        for record in sorted_records
        if normalize_text(record["assigned_to_name"])
    }
    unique_trackers = {
        normalize_text(record["tracker_name"])
        for record in sorted_records
        if normalize_text(record["tracker_name"])
    }
    matched_issue_count = match_counts["exact"] + match_counts["alias"]

    yearly_reports = []
    if issues:
        yearly_reports.append(
            {
                "year": "",
                "total_hours": 0.0,
                "total_hours_label": "0",
                "total_entries": 0,
                "issue_count": len(issues),
                "matched_issue_count": matched_issue_count,
                "department_count": len(unique_departments),
                "departments": [],
                "requesters": [],
                "companies": [],
                "issues": issues,
                "unmatched_requesters": [],
                "match_breakdown": {
                    "exact": match_counts["exact"],
                    "alias": match_counts["alias"],
                    "unmatched": match_counts["unmatched"],
                },
            }
        )

    return {
        "summary": {
            "unique_issue_count": len(issues),
            "years_covered": 1 if issues else 0,
            "matched_issue_count": matched_issue_count,
            "unique_department_count": len(unique_departments),
            "unique_assignee_count": len(unique_assignees),
            "unique_tracker_count": len(unique_trackers),
        },
        "yearly_reports": yearly_reports,
        "directory_summary": build_directory_summary(user_directory, user_aliases),
    }


def resolve_filters(query: dict[str, list[str]]) -> tuple[date | None, date | None]:
    raw_from = query.get("from", [""])[0]
    raw_to = query.get("to", [""])[0]

    try:
        spent_from = parse_iso_date(raw_from)
        spent_to = parse_iso_date(raw_to)
    except ValueError as exc:
        raise ValueError("Date filters must use YYYY-MM-DD format") from exc

    if spent_from and spent_to and spent_from > spent_to:
        raise ValueError("The start date must be earlier than or equal to the end date")

    return spent_from, spent_to


def list_report_users() -> dict[str, Any]:
    redmine_client = RedmineClient(load_redmine_config())
    current_user = redmine_client.get_current_user()
    current_user_id = int(current_user["id"])

    users = [current_user]
    directory_warning = ""
    try:
        users = redmine_client.list_users(status=1)
    except Exception as exc:
        directory_warning = str(exc)

    deduped_users: dict[int, dict[str, Any]] = {}
    for user in users + [current_user]:
        user_id = int(user.get("id") or 0)
        if not user_id:
            continue
        deduped_users[user_id] = serialize_redmine_user(user)

    sorted_users = sorted(
        deduped_users.values(),
        key=lambda item: (item["name"].casefold(), item["login"].casefold(), item["id"]),
    )

    return {
        "current_user": serialize_redmine_user(current_user),
        "users": sorted_users,
        "can_select_others": any(user["id"] != current_user_id for user in sorted_users),
        "warning": directory_warning,
    }


def build_report(query: dict[str, list[str]]) -> dict[str, Any]:
    spent_from, spent_to = resolve_filters(query)
    redmine_client = RedmineClient(load_redmine_config())
    superset_client = SupersetClient(load_superset_config())
    current_user = redmine_client.get_current_user()
    current_user_id = int(current_user["id"])
    report_user_ids = resolve_report_user_ids(query, current_user_id)
    scope_mode = "assigned" if not spent_from and not spent_to else "time_entries"

    with ThreadPoolExecutor(max_workers=max(2, len(report_user_ids) + 1)) as executor:
        directory_future = executor.submit(load_user_directory_cached, superset_client)
        raw_entries: list[dict[str, Any]] = []
        assigned_issue_details: dict[int, dict[str, Any]] = {}

        if scope_mode == "assigned":
            issue_futures = {
                executor.submit(redmine_client.list_assigned_issues, user_id): user_id
                for user_id in report_user_ids
            }
            for future in issue_futures:
                for issue in future.result():
                    issue_id = int(issue.get("id") or 0)
                    if issue_id:
                        assigned_issue_details[issue_id] = issue
        else:
            entry_futures = {
                executor.submit(redmine_client.list_time_entries, user_id, spent_from, spent_to): user_id
                for user_id in report_user_ids
            }
            for future in entry_futures:
                raw_entries.extend(future.result())

        user_directory = directory_future.result()

    user_aliases = load_user_aliases()
    selected_users = [
        current_user if user_id == current_user_id else redmine_client.get_user(user_id)
        for user_id in report_user_ids
    ]

    if scope_mode == "assigned":
        issue_insights = build_assigned_issue_insights(
            issue_details=assigned_issue_details,
            user_directory=user_directory,
            user_aliases=user_aliases,
            base_url=redmine_client.base_url,
        )
        grouped = {
            "summary": {
                "total_hours": 0.0,
                "total_hours_label": "0",
                "total_entries": 0,
                "unique_project_count": len(
                    {
                        normalize_text((issue.get("project") or {}).get("name"))
                        for issue in assigned_issue_details.values()
                        if isinstance(issue, dict)
                        and normalize_text((issue.get("project") or {}).get("name"))
                    }
                ),
                "unique_activity_count": 0,
            },
            "entries": [],
        }
    else:
        grouped = summarize_entries(raw_entries, base_url=redmine_client.base_url)
        issue_ids = {int(entry["issue_id"]) for entry in grouped["issue_entries"] if entry.get("issue_id")}
        issue_details = redmine_client.get_issues(issue_ids)
        issue_insights = build_issue_insights(
            entries=grouped["issue_entries"],
            issue_details=issue_details,
            user_directory=user_directory,
            user_aliases=user_aliases,
            base_url=redmine_client.base_url,
        )

    grouped["summary"].update(issue_insights["summary"])
    primary_user = selected_users[0]

    return {
        "generated_at": timestamp_now(),
        "user": serialize_redmine_user(primary_user),
        "users": [serialize_redmine_user(user) for user in selected_users],
        "viewer": serialize_redmine_user(current_user),
        "filters": {
            "from": spent_from.isoformat() if spent_from else "",
            "to": spent_to.isoformat() if spent_to else "",
            "range_label": build_range_label(spent_from, spent_to),
            "scope_mode": scope_mode,
            "user_id": str(primary_user["id"]),
            "user_ids": [str(user_id) for user_id in report_user_ids],
            "user_name": ", ".join(display_name(user) for user in selected_users),
        },
        "summary": grouped["summary"],
        "entries": grouped["entries"],
        "yearly_reports": issue_insights["yearly_reports"],
        "directory_summary": issue_insights["directory_summary"],
    }
