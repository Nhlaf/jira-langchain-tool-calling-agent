"""Business-level LangChain tools backed by the Jira client."""

from typing import Any

from langchain_core.tools import tool

from tools.jira_client import JiraClient


def get_jira_client() -> JiraClient:
    """Create a configured client lazily so importing tools needs no credentials."""
    return JiraClient.from_environment()


@tool
def get_issue_details(issue_key: str) -> dict[str, Any]:
    """Retrieve details for an existing Jira issue using its issue key, such as SCRUM-123."""
    return get_jira_client().get_issue(issue_key)


@tool
def search_issues(jql: str, max_results: int = 50) -> dict[str, Any]:
    """Search Jira issues with a JQL query. Use explicit project, status, assignee, or issue-type criteria from the user; returns up to 100 matching issues."""
    return get_jira_client().search_issues(jql, max_results)


@tool
def create_story(project_key: str, summary: str, description: str = "") -> dict[str, Any]:
    """Create a Jira Story. Required information: project key, summary, and description. Always pass the description from the user's request."""
    return get_jira_client().create_issue(project_key, summary, description, "Story")


@tool
def create_bug(project_key: str, summary: str, description: str = "") -> dict[str, Any]:
    """Create a Jira Bug for a defect or broken behavior. Required information: project key, summary, and description. Always pass the description from the user's request."""
    return get_jira_client().create_issue(project_key, summary, description, "Bug")


@tool
def create_task(project_key: str, summary: str, description: str = "") -> dict[str, Any]:
    """Create a Jira Task. Required information: project key, summary, and description. Always pass the description from the user's request."""
    return get_jira_client().create_issue(project_key, summary, description, "Task")


JIRA_TOOLS = [
    get_issue_details,
    search_issues,
    create_story,
    create_bug,
    create_task,
]
