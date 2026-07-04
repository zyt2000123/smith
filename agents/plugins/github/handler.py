"""GitHub webhook event handler.

Parses GitHub webhook payloads and converts supported events into
agent task dicts with a normalized structure.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Events we handle
_SUPPORTED_ACTIONS: dict[str, set[str]] = {
    "issues": {"opened", "edited", "labeled"},
    "pull_request": {"opened", "synchronize", "review_requested"},
}


async def handle(event: dict) -> None:
    """Entry point called by the plugin trigger.

    ``event`` is the raw webhook payload with an added ``_github_event``
    key indicating the X-GitHub-Event header value.
    """
    event_type = event.get("_github_event", "")
    action = event.get("action", "")

    if event_type not in _SUPPORTED_ACTIONS:
        log.debug("Ignoring unsupported GitHub event: %s", event_type)
        return

    if action not in _SUPPORTED_ACTIONS[event_type]:
        log.debug("Ignoring action %s for event %s", action, event_type)
        return

    task = _parse_event(event_type, action, event)
    if task is None:
        return

    # Store parsed task on the event so the plugin service can pick it up.
    # The plugin service reads event["_task"] after handle() returns.
    event["_task"] = task
    log.info("GitHub plugin created task: %s", task.get("title", ""))


def _parse_event(event_type: str, action: str, payload: dict) -> dict | None:
    if event_type == "issues":
        return _parse_issue(action, payload)
    if event_type == "pull_request":
        return _parse_pull_request(action, payload)
    return None


def _parse_issue(action: str, payload: dict) -> dict:
    issue = payload.get("issue", {})
    repo = payload.get("repository", {})
    return {
        "title": f"[GitHub Issue] {repo.get('full_name', '')}#{issue.get('number', '')}",
        "instruction": (
            f"A GitHub issue was {action}.\n\n"
            f"Repository: {repo.get('full_name', '')}\n"
            f"Issue #{issue.get('number', '')}: {issue.get('title', '')}\n"
            f"Author: {issue.get('user', {}).get('login', '')}\n"
            f"URL: {issue.get('html_url', '')}\n\n"
            f"Body:\n{issue.get('body', '') or '(empty)'}\n\n"
            f"Labels: {', '.join(l.get('name', '') for l in issue.get('labels', []))}\n\n"
            f"Please analyze this issue and draft a response."
        ),
        "source": "github",
        "source_event": f"issues.{action}",
    }


def _parse_pull_request(action: str, payload: dict) -> dict:
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})
    return {
        "title": f"[GitHub PR] {repo.get('full_name', '')}#{pr.get('number', '')}",
        "instruction": (
            f"A GitHub pull request was {action}.\n\n"
            f"Repository: {repo.get('full_name', '')}\n"
            f"PR #{pr.get('number', '')}: {pr.get('title', '')}\n"
            f"Author: {pr.get('user', {}).get('login', '')}\n"
            f"URL: {pr.get('html_url', '')}\n"
            f"Branch: {pr.get('head', {}).get('ref', '')} -> {pr.get('base', {}).get('ref', '')}\n\n"
            f"Body:\n{pr.get('body', '') or '(empty)'}\n\n"
            f"Please review this pull request."
        ),
        "source": "github",
        "source_event": f"pull_request.{action}",
    }
