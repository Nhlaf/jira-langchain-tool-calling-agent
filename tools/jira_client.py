"""HTTP client that contains all Jira REST API implementation details."""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Any

import requests


class JiraClientError(Exception):
    """A user-safe error returned by the Jira client."""


class JiraConfigurationError(JiraClientError):
    """Raised when required Jira environment variables are missing."""


class JiraClient:
    """Small Jira Cloud REST client used only by the tool layer."""

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        session: requests.Session | None = None,
        timeout: int = 20,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth = (email, api_token)
        self.session = session or requests.Session()
        self.timeout = timeout

    @classmethod
    def from_environment(cls) -> "JiraClient":
        """Build a client from Jira credentials in the process environment."""
        required = ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            names = ", ".join(missing)
            raise JiraConfigurationError(
                f"Missing Jira configuration: {names}. Set these values in your .env file."
            )

        return cls(
            base_url=os.environ["JIRA_BASE_URL"],
            email=os.environ["JIRA_EMAIL"],
            api_token=os.environ["JIRA_API_TOKEN"],
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/rest/api/3/{path.lstrip('/')}"
        try:
            response = self.session.request(
                method,
                url,
                auth=self.auth,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                params=params,
                json=json_body,
                timeout=self.timeout,
            )
        except requests.RequestException as error:
            raise JiraClientError(
                "Jira is unavailable right now. Check the Jira URL and your network connection."
            ) from error

        if response.status_code in (401, 403):
            raise JiraClientError(
                "Jira rejected the credentials or the account lacks permission for this action."
            )
        if response.status_code == 404:
            raise JiraClientError("Jira could not find that issue or project.")
        if not 200 <= response.status_code < 300:
            detail = ""
            try:
                payload = response.json()
                messages = payload.get("errorMessages", [])
                errors = payload.get("errors", {})
                detail = "; ".join(str(message) for message in messages)
                if errors:
                    field_errors = "; ".join(
                        f"{field}: {message}" for field, message in errors.items()
                    )
                    detail = f"{detail}; {field_errors}".strip("; ")
            except (ValueError, AttributeError):
                pass
            if response.status_code == 400 and detail:
                raise JiraClientError(f"Jira could not complete the request: {detail}")
            raise JiraClientError(
                f"Jira could not complete the request (HTTP {response.status_code})."
            )

        if response.status_code == 204:
            return {}
        try:
            result = response.json()
        except ValueError as error:
            raise JiraClientError("Jira returned an unreadable response.") from error
        if not isinstance(result, dict):
            raise JiraClientError("Jira returned an unexpected response format.")
        return result

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*-\d+", issue_key.strip()):
            raise ValueError("Enter an issue key such as PAY-123.")
        result = self._request(
            "GET",
            f"issue/{issue_key.strip()}",
            params={"fields": "summary,description,status,issuetype,assignee,reporter,priority,project"},
        )
        fields = result.get("fields", {})
        return {
            "key": result.get("key", issue_key.upper()),
            "summary": fields.get("summary"),
            "description": fields.get("description"),
            "status": (fields.get("status") or {}).get("name"),
            "issue_type": (fields.get("issuetype") or {}).get("name"),
            "assignee": (fields.get("assignee") or {}).get("displayName"),
            "reporter": (fields.get("reporter") or {}).get("displayName"),
            "priority": (fields.get("priority") or {}).get("name"),
            "project": (fields.get("project") or {}).get("name"),
        }

    def search_issues(self, jql: str, max_results: int = 50) -> dict[str, Any]:
        """Search Jira with JQL and return a compact first-page result set."""
        if not jql.strip():
            raise ValueError("A JQL query is required.")
        if not 1 <= max_results <= 100:
            raise ValueError("max_results must be between 1 and 100.")

        result = self._request(
            "POST",
            "search/jql",
            json_body={
                "jql": jql.strip(),
                "fields": ["summary", "status", "issuetype", "assignee", "project"],
                "maxResults": max_results,
            },
        )
        issues = result.get("issues", [])
        if not isinstance(issues, list):
            raise JiraClientError("Jira returned an unexpected issue search format.")

        return {
            "total": result.get("total", len(issues)),
            "issues": [
                {
                    "key": issue.get("key"),
                    "summary": (issue.get("fields") or {}).get("summary"),
                    "status": ((issue.get("fields") or {}).get("status") or {}).get("name"),
                    "issue_type": ((issue.get("fields") or {}).get("issuetype") or {}).get("name"),
                    "assignee": ((issue.get("fields") or {}).get("assignee") or {}).get("displayName"),
                    "project": ((issue.get("fields") or {}).get("project") or {}).get("name"),
                }
                for issue in issues
                if isinstance(issue, dict)
            ],
        }

    def get_project(self, project_key: str) -> dict[str, Any]:
        self._validate_project_key(project_key)
        result = self._request("GET", f"project/{project_key.strip()}")
        return {
            "key": result.get("key", project_key.strip().upper()),
            "name": result.get("name"),
            "description": result.get("description"),
            "project_type": result.get("projectTypeKey"),
            "lead": (result.get("lead") or {}).get("displayName"),
        }

    def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str,
    ) -> dict[str, Any]:
        self._validate_project_key(project_key)
        if not summary.strip():
            raise ValueError("An issue summary is required.")
        if not description.strip():
            raise ValueError("An issue description is required.")
        if not issue_type.strip():
            raise ValueError("An issue type is required.")

        result = self._request(
            "POST",
            "issue",
            json_body={
                "fields": {
                    "project": {"key": project_key.strip()},
                    "summary": summary.strip(),
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": description.strip()}],
                            }
                        ],
                    },
                    "issuetype": {"name": issue_type.strip()},
                }
            },
        )
        return {"key": result.get("key"), "id": result.get("id"), "self": result.get("self")}

    def get_project_issues(self, project_key: str) -> list[dict[str, Any]]:
        """Fetch project issues in pages for an accurate project summary."""
        self._validate_project_key(project_key)
        issues: list[dict[str, Any]] = []
        start_at = 0
        page_size = 100
        total = 1
        while start_at < total:
            result = self._request(
                "POST",
                "search/jql",
                json_body={
                    "jql": f'project = "{project_key.strip()}" ORDER BY created DESC',
                    "fields": ["issuetype", "status"],
                    "maxResults": page_size,
                    "startAt": start_at,
                },
            )
            page = result.get("issues", [])
            if not isinstance(page, list):
                raise JiraClientError("Jira returned an unexpected project report format.")
            issues.extend(issue for issue in page if isinstance(issue, dict))
            total = int(result.get("total", len(issues)))
            if not page:
                break
            start_at += len(page)
        return issues

    @staticmethod
    def _validate_project_key(project_key: str) -> None:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", project_key.strip()):
            raise ValueError("Enter a valid Jira project key, such as PAY.")

    @staticmethod
    def summarize_project_issues(
        project_key: str, issues: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Create counts by issue type and status from fetched project issues."""
        issue_types: Counter[str] = Counter()
        statuses: Counter[str] = Counter()
        open_count = 0
        closed_count = 0

        for issue in issues:
            fields = issue.get("fields", {})
            issue_type = (fields.get("issuetype") or {}).get("name", "Unknown")
            status = fields.get("status") or {}
            status_name = status.get("name", "Unknown")
            category = (status.get("statusCategory") or {}).get("key", "")
            issue_types[issue_type] += 1
            statuses[status_name] += 1
            if category == "done":
                closed_count += 1
            else:
                open_count += 1

        return {
            "project_key": project_key.strip().upper(),
            "total_issues": len(issues),
            "open_issues": open_count,
            "closed_issues": closed_count,
            "bugs": sum(count for name, count in issue_types.items() if name.lower() == "bug"),
            "tasks": sum(count for name, count in issue_types.items() if name.lower() == "task"),
            "stories": sum(count for name, count in issue_types.items() if name.lower() == "story"),
            "issues_by_type": dict(issue_types),
            "issues_by_status": dict(statuses),
            "report_scope": "Counts are based on all project issues returned by Jira at report time.",
        }