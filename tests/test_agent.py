from __future__ import annotations

from langchain_core.messages import AIMessage

from agent.jira_agent import JiraAgent
from tools.jira_tools import JIRA_TOOLS


class FakeModel:
    def __init__(self, responses: list[AIMessage]) -> None:
        self.responses = iter(responses)
        self.bound_tools = []
        self.messages_seen = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def invoke(self, messages):
        self.messages_seen.append(list(messages))
        return next(self.responses)


def test_agent_binds_five_tools_and_executes_llm_selected_tool(monkeypatch) -> None:
    from tools import jira_tools

    fake_client = type("FakeClient", (), {"get_issue": lambda self, key: {"key": key, "summary": "Button fails"}})()
    monkeypatch.setattr(jira_tools, "get_jira_client", lambda: fake_client)
    model = FakeModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_issue_details",
                        "args": {"issue_key": "PAY-12"},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="PAY-12 is titled Button fails."),
        ]
    )
    agent = JiraAgent(model=model)
    selected: list[str] = []

    result = agent.run("Tell me the details of PAY-12.", on_tool_selected=selected.append)

    assert {tool.name for tool in model.bound_tools} == {
        "get_issue_details",
        "search_issues",
        "create_story",
        "create_bug",
        "create_task",
    }
    assert len(model.bound_tools) == 5
    assert selected == ["get_issue_details"]
    assert result.selected_tools == ["get_issue_details"]
    assert result.answer == "PAY-12 is titled Button fails."
    assert model.messages_seen[1][-1].content == '{"key": "PAY-12", "summary": "Button fails"}'


def test_tool_schemas_use_business_inputs() -> None:
    tools = {jira_tool.name: jira_tool for jira_tool in JIRA_TOOLS}

    assert set(tools) == {
        "get_issue_details",
        "search_issues",
        "create_story",
        "create_bug",
        "create_task",
    }
    assert set(tools["get_issue_details"].args) == {"issue_key"}
    assert set(tools["search_issues"].args) == {"jql", "max_results"}
    assert set(tools["create_story"].args) == {"project_key", "summary", "description"}
    assert set(tools["create_bug"].args) == {"project_key", "summary", "description"}
    assert set(tools["create_task"].args) == {"project_key", "summary", "description"}
    for name in ("create_story", "create_bug", "create_task"):
        assert "description" not in tools[name].args_schema.model_json_schema()["required"]


def test_agent_retries_create_task_when_description_is_omitted(monkeypatch) -> None:
    from tools import jira_tools

    create_calls = []

    class FakeClient:
        def create_issue(self, project_key, summary, description, issue_type):
            create_calls.append((project_key, summary, description, issue_type))
            return {"key": "SCRUM-42"}

    monkeypatch.setattr(jira_tools, "get_jira_client", FakeClient)
    model = FakeModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_task",
                        "args": {
                            "project_key": "SCRUM",
                            "summary": "Update payment validation",
                        },
                        "id": "call-missing-description",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_task",
                        "args": {
                            "project_key": "SCRUM",
                            "summary": "Update payment validation",
                            "description": "Validate payment fields before submission.",
                        },
                        "id": "call-with-description",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Created SCRUM-42."),
        ]
    )
    agent = JiraAgent(model=model)
    selected: list[str] = []

    result = agent.run(
        "Create a Task in SCRUM titled 'Update payment validation'. "
        "Description: Validate payment fields before submission.",
        on_tool_selected=selected.append,
    )

    assert create_calls == [
        ("SCRUM", "Update payment validation", "Validate payment fields before submission.", "Task")
    ]
    assert result.selected_tools == ["create_task", "create_task"]
    assert selected == ["create_task"]
    assert "description is required" in model.messages_seen[1][-1].content
    assert result.answer == "Created SCRUM-42."


def test_agent_stops_repeated_create_task_calls_without_description(monkeypatch) -> None:
    from tools import jira_tools

    create_calls = []

    class FakeClient:
        def create_issue(self, *args):
            create_calls.append(args)
            return {"key": "SCRUM-42"}

    monkeypatch.setattr(jira_tools, "get_jira_client", FakeClient)
    missing_description_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "create_task",
                "args": {
                    "project_key": "SCRUM",
                    "summary": "Update payment validation",
                },
                "id": "call-missing-description",
                "type": "tool_call",
            }
        ],
    )
    model = FakeModel([missing_description_call, missing_description_call])
    agent = JiraAgent(model=model)

    result = agent.run("Create a task in SCRUM with a description.")

    assert create_calls == []
    assert len(model.messages_seen) == 2
    assert "repeatedly omitted" in result.answer


def test_agent_returns_user_facing_message_at_tool_round_limit(monkeypatch) -> None:
    from tools import jira_tools

    project_calls = []

    class FakeClient:
        def search_issues(self, jql, max_results):
            project_calls.append((jql, max_results))
            return {"total": 0, "issues": []}

    monkeypatch.setattr(jira_tools, "get_jira_client", FakeClient)
    responses = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "search_issues",
                    "args": {"jql": "project = SCRUM", "max_results": 50},
                    "id": f"call-{index}",
                    "type": "tool_call",
                }
            ],
        )
        for index in range(3)
    ]
    model = FakeModel(responses)
    agent = JiraAgent(model=model)

    result = agent.run("Search project SCRUM.", max_tool_rounds=2)

    assert project_calls == [("project = SCRUM", 50), ("project = SCRUM", 50)]
    assert "after 2 Jira tool rounds" in result.answer