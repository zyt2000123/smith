# Skill: GitHub Issue Responder

## Purpose

Analyze incoming GitHub issues and draft helpful responses.

## When to Use

When a GitHub issue webhook triggers a task containing issue details.

## Workflow

1. Read the issue title, body, and labels carefully.
2. Identify whether the issue is a bug report, feature request, or question.
3. For **bug reports**: ask clarifying questions about reproduction steps, environment, and expected behavior.
4. For **feature requests**: acknowledge the idea, assess feasibility, and suggest next steps.
5. For **questions**: provide a clear, concise answer based on available context.

## Output Format

Draft a professional, friendly response in Markdown suitable for posting as a GitHub comment.
Include:
- Acknowledgment of the issue
- Category classification (bug / feature / question)
- Specific follow-up questions or suggested actions
- Relevant links or documentation references if available

## Constraints

- Keep responses concise (under 300 words)
- Be welcoming to new contributors
- Do not make promises about timelines
- Do not close or label the issue — only draft a comment
