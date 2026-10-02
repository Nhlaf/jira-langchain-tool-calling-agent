"""Command-line demonstration of the Jira LangChain tool-calling agent."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from agent.jira_agent import AgentConfigurationError, JiraAgent
from tools.jira_client import JiraConfigurationError, JiraClient


def validate_configuration() -> None:
    """Fail before starting the demo when required service settings are absent."""
    project_root = Path(__file__).resolve().parent
    load_dotenv(project_root / ".env")
    missing = [
        name
        for name in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "GROQ_API_KEY")
        if not os.getenv(name)
    ]
    if missing:
        raise ValueError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Add them to .env using .env.example as a guide."
        )
    JiraClient.from_environment()


def main() -> None:
    print("Jira LangChain Agent")
    print("====================")
    try:
        validate_configuration()
        agent = JiraAgent()
    except (ValueError, JiraConfigurationError, AgentConfigurationError) as error:
        print(f"Configuration error: {error}")
        return

    print("Enter a Jira request, or type 'quit' to exit.")
    while True:
        try:
            user_request = input("\nUser: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if user_request.lower() in {"quit", "exit"}:
            break
        if not user_request:
            continue

        print()

        def show_tool(tool_name: str) -> None:
            print(f"Selected tool: {tool_name}")
            print("Executing Jira operation...")

        try:
            result = agent.run(user_request, on_tool_selected=show_tool)
            print(f"\nAssistant: {result.answer}")
        except Exception as error:
            print(f"\nAssistant: The request could not be completed: {error}")


if __name__ == "__main__":
    main()