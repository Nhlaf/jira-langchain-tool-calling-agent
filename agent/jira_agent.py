"""LLM tool-selection loop for the Jira assistant."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_groq import ChatGroq

from tools.jira_client import JiraClientError
from tools.jira_tools import JIRA_TOOLS


class AgentConfigurationError(Exception):
    """Raised when the LLM cannot be configured."""


@dataclass
class AgentResponse:
    """Final assistant text and the tools selected during this request."""

    answer: str
    selected_tools: list[str]


class JiraAgent:
    """Bind Jira tools to an LLM and execute only its declared tool calls."""

    def __init__(
        self,
        model: Any | None = None,
        tools: list[BaseTool] | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        project_root = Path(__file__).resolve().parent.parent
        load_dotenv(project_root / ".env")
        self.tools = tools if tools is not None else list(JIRA_TOOLS)
        self.tools_by_name = {jira_tool.name: jira_tool for jira_tool in self.tools}
        if model is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise AgentConfigurationError(
                    "Missing GROQ_API_KEY. Add your Groq API key to the .env file."
                )
            model = ChatGroq(
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                api_key=api_key,
                temperature=0,
            )

        path = prompt_path or project_root / "prompts" / "jira_agent_prompt.md"
        self.system_prompt = path.read_text(encoding="utf-8")
        self.model_with_tools = model.bind_tools(self.tools)

    def run(
        self,
        user_request: str,
        on_tool_selected: Callable[[str], None] | None = None,
        max_tool_rounds: int = 5,
    ) -> AgentResponse:
        """Ask the LLM to select tools, execute them, and return its final answer."""
        messages: list[Any] = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_request),
        ]
        selected_tools: list[str] = []
        incomplete_description_calls = 0

        for tool_round in range(max_tool_rounds + 1):
            response = self.model_with_tools.invoke(messages)
            messages.append(response)
            tool_calls = getattr(response, "tool_calls", []) or []
            if not tool_calls:
                answer = response.content
                if not isinstance(answer, str):
                    answer = json.dumps(answer, ensure_ascii=True, default=str)
                return AgentResponse(answer=answer, selected_tools=selected_tools)
            if tool_round == max_tool_rounds:
                return AgentResponse(
                    answer=(
                        f"I couldn't finish the request after {max_tool_rounds} Jira tool rounds. "
                        "Check Jira before retrying any request that creates an issue."
                    ),
                    selected_tools=selected_tools,
                )

            for call in tool_calls:
                tool_name = call.get("name", "")
                tool_call_id = call.get("id", tool_name)
                selected_tools.append(tool_name)
                jira_tool = self.tools_by_name.get(tool_name)
                if jira_tool is None:
                    result: Any = {"error": f"The model selected an unavailable tool: {tool_name}."}
                elif tool_name in {"create_story", "create_bug", "create_task"} and not str(
                    call.get("args", {}).get("description", "")
                ).strip():
                    incomplete_description_calls += 1
                    if incomplete_description_calls > 1:
                        return AgentResponse(
                            answer=(
                                "I couldn't create the issue because the model repeatedly omitted "
                                "the required description. Please retry with the description "
                                "included explicitly."
                            ),
                            selected_tools=selected_tools,
                        )
                    result = {
                        "error": (
                            "The description is required. Do not execute this request yet. "
                            f"Retry {tool_name} with the description from the user's request. "
                            "If the user did not provide one, ask them for it."
                        )
                    }
                else:
                    if on_tool_selected is not None:
                        on_tool_selected(tool_name)
                    try:
                        result = jira_tool.invoke(call.get("args", {}))
                    except (JiraClientError, ValueError) as error:
                        result = {"error": str(error)}
                if not isinstance(result, str):
                    result = json.dumps(result, ensure_ascii=True, default=str)
                messages.append(
                    ToolMessage(content=result, name=tool_name, tool_call_id=tool_call_id)
                )

        return AgentResponse(
            answer=(
                f"I couldn't finish the request after {max_tool_rounds} Jira tool rounds. "
                "Check Jira before retrying any request that creates an issue."
            ),
            selected_tools=selected_tools,
        )