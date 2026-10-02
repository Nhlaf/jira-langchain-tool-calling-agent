# Jira Tools and Example Questions

The CLI assistant chooses one of five LangChain tools for each request. Enter a request at the `User:` prompt in `python main.py`.

## Available Tools

| Tool | What it does | Required information |
| --- | --- | --- |
| `get_issue_details` | Retrieves an existing issue's summary, description, status, type, assignee, reporter, priority, and project. | Issue key, such as `SCRUM-123` |
| `search_issues` | Searches Jira with JQL and returns up to 100 matching issues. | JQL query; result limit is optional and defaults to 50 |
| `create_story` | Creates a Jira Story. | Project key, summary, and description |
| `create_bug` | Creates a Jira Bug. | Project key, summary, and description |
| `create_task` | Creates a Jira Task. | Project key, summary, and description |

## Example Questions

### Get Issue Details

Use an existing issue key, including its number:

> Tell me the details of issue SCRUM-123.

`SCRUM` by itself is a project key, not an issue key. If you do not know an issue key, use Search Issues first.

### Search Issues

Use natural language or provide JQL directly:

> Find open tasks in project SCRUM.

> Search Jira with JQL: `project = SCRUM AND issuetype = Task AND statusCategory != Done`

> Find bugs in SCRUM assigned to me.

The search returns at most 100 results per request. The default limit is 50.

### Create a Story

> Create a story in SCRUM with the summary "View payment history" and description "As a customer, I want to view my previous payments so I can track my transactions."

### Create a Bug

> Create a bug in SCRUM with the summary "Payment button fails" and description "Submitting the payment form does not complete checkout."

### Create a Task

> Create a task in SCRUM with the summary "Update payment validation" and description "Validate payment fields before submission."

## Notes

- Use the project key, for example `SCRUM`, for searches and issue creation. Use a full issue key, for example `SCRUM-123`, to retrieve one issue.
- Include a project key, summary, and description in every create request. The create tools set the issue type automatically.
- Creating a Story, Bug, or Task makes a real change in Jira. Check Jira for duplicates before retrying a request that may have succeeded.
- Search results and issue details depend on the permissions of the Jira account configured for the application.