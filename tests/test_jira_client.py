from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from tools.jira_client import JiraClient, JiraClientError
from tools import jira_tools


def response(status_code: int, payload: object) -> Mock:
    mock_response = Mock()
    mock_response.status_code = status_code
    mock_response.json.return_value = payload
    return mock_response


def test_get_issue_uses_client_and_returns_clean_details() -> None:
    session = Mock()
    session.request.return_value = response(
        200,
        {
            "key": "PAY-12",
            "fields": {
                "summary": "Button fails",
                "description": "Cannot submit",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "assignee": None,
                "reporter": {"displayName": "Sam"},
                "priority": {"name": "High"},
                "project": {"name": "Payments"},
            },
        },
    )
    client = JiraClient("https://example.atlassian.net/", "user", "token", session)

    result = client.get_issue("PAY-12")

    assert result["key"] == "PAY-12"
    assert result["summary"] == "Button fails"
    assert result["assignee"] is None
    assert session.request.call_args.args[:2] == (
        "GET",
        "https://example.atlassian.net/rest/api/3/issue/PAY-12",
    )
    assert session.request.call_args.kwargs["auth"] == ("user", "token")


def test_create_issue_builds_payload_inside_client() -> None:
    session = Mock()
    session.request.return_value = response(201, {"key": "PAY-13", "id": "13"})
    client = JiraClient("https://example.atlassian.net", "user", "token", session)

    result = client.create_issue("PAY", "New task", "Details", "Task")

    assert result["key"] == "PAY-13"
    assert session.request.call_args.kwargs["json"]["fields"]["issuetype"] == {"name": "Task"}
    assert session.request.call_args.kwargs["json"]["fields"]["description"] == {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Details"}]}
        ],
    }


def test_search_issues_uses_jql_and_returns_compact_issue_data() -> None:
    session = Mock()
    session.request.return_value = response(
        200,
        {
            "total": 1,
            "issues": [
                {
                    "key": "PAY-13",
                    "fields": {
                        "summary": "New task",
                        "status": {"name": "Open"},
                        "issuetype": {"name": "Task"},
                        "assignee": {"displayName": "Sam"},
                        "project": {"name": "Payments"},
                    },
                }
            ],
        },
    )
    client = JiraClient("https://example.atlassian.net", "user", "token", session)

    result = client.search_issues("project = PAY", max_results=10)

    assert result == {
        "total": 1,
        "issues": [
            {
                "key": "PAY-13",
                "summary": "New task",
                "status": "Open",
                "issue_type": "Task",
                "assignee": "Sam",
                "project": "Payments",
            }
        ],
    }
    assert session.request.call_args.args[:2] == (
        "POST",
        "https://example.atlassian.net/rest/api/3/search/jql",
    )
    assert session.request.call_args.kwargs["json"]["jql"] == "project = PAY"


@pytest.mark.parametrize(
    ("status_code", "message"),
    [
        (401, "credentials"),
        (403, "permission"),
        (404, "find"),
        (503, "HTTP 503"),
    ],
)
def test_http_errors_are_translated(status_code: int, message: str) -> None:
    session = Mock()
    session.request.return_value = response(status_code, {})
    client = JiraClient("https://example.atlassian.net", "user", "token", session)

    with pytest.raises(JiraClientError, match=message):
        client.get_project("PAY")


def test_network_errors_are_translated() -> None:
    session = Mock()
    session.request.side_effect = requests.ConnectionError("private network detail")
    client = JiraClient("https://example.atlassian.net", "user", "token", session)

    with pytest.raises(JiraClientError, match="Jira is unavailable"):
        client.get_project("PAY")


def test_invalid_issue_key_is_rejected_before_http_call() -> None:
    session = Mock()
    client = JiraClient("https://example.atlassian.net", "user", "token", session)

    with pytest.raises(ValueError, match="issue key"):
        client.get_issue("not an issue key")
    session.request.assert_not_called()


@pytest.mark.parametrize(
    ("tool_name", "issue_type"),
    [("create_story", "Story"), ("create_bug", "Bug"), ("create_task", "Task")],
)
def test_create_tools_fix_issue_type(
    monkeypatch: pytest.MonkeyPatch, tool_name: str, issue_type: str
) -> None:
    client = Mock()
    monkeypatch.setattr(jira_tools, "get_jira_client", lambda: client)

    result = getattr(jira_tools, tool_name).invoke(
        {
            "project_key": "PAY",
            "summary": "Payment update",
            "description": "Details for this Jira issue.",
        }
    )

    assert result == client.create_issue.return_value
    client.create_issue.assert_called_once_with(
        "PAY", "Payment update", "Details for this Jira issue.", issue_type
    )


def test_report_counts_types_and_status_categories() -> None:
    session = Mock()
    session.request.return_value = response(
        200,
        {
            "total": 2,
            "issues": [
                {"fields": {"issuetype": {"name": "Bug"}, "status": {"name": "Open", "statusCategory": {"key": "new"}}}},
                {"fields": {"issuetype": {"name": "Task"}, "status": {"name": "Done", "statusCategory": {"key": "done"}}}},
            ],
        },
    )
    client = JiraClient("https://example.atlassian.net", "user", "token", session)
    issues = client.get_project_issues("PAY")

    report = client.summarize_project_issues("PAY", issues)

    assert (report["total_issues"], report["open_issues"], report["closed_issues"]) == (2, 1, 1)
    assert report["bugs"] == 1
    assert report["tasks"] == 1