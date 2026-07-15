from __future__ import annotations

"""Git workflow tool provider — branch, commit, push, worktree operations.

Uses subprocess for all git commands. Validates inputs to prevent shell
injection. Checks for sensitive files before staging.
"""

import os
import re
import subprocess

TOOL_META = {
    "name": "git_ops",
    "description": "Git workflow operations: status, diff, branch, commit, push, worktree management, and repo discovery.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "status",
                    "diff",
                    "branch_create",
                    "commit",
                    "push",
                    "worktree_create",
                    "worktree_remove",
                    "discover",
                ],
                "description": "The git operation to perform",
            },
            "cwd": {
                "type": "string",
                "description": "Repository working directory (defaults to current directory)",
            },
            "branch": {
                "type": "string",
                "description": "Branch name (for branch_create, push)",
            },
            "message": {
                "type": "string",
                "description": "Commit message (for commit)",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Files to stage (for commit; omit to stage all tracked changes)",
            },
            "staged": {
                "type": "boolean",
                "description": "Show staged changes only (for diff, default false)",
                "default": False,
            },
            "path": {
                "type": "string",
                "description": "Worktree path (for worktree_remove)",
            },
        },
        "required": ["action"],
    },
    "path_args": ["cwd", "path"],
    "list_path_args": ["files"],
    "is_write_tool": True,
    "permission_level": "write",
    "approval_policy": "policy",
    "read_actions": ["status", "diff", "discover"],
    "side_effect": "external",
    "concurrency": "serial",
    "execution_environment": "host",
}

MAX_OUTPUT = 10 * 1024  # 10KB

# Branch/tag name validation: alphanumeric, dash, underscore, dot, slash
_SAFE_REF = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,200}$")

# Patterns for sensitive files that should not be staged
_SENSITIVE_PATTERNS = re.compile(
    r"(?i)"
    r"(^|/)\.env($|\.)"
    r"|(^|/)credentials"
    r"|(^|/)secrets?"
    r"|(^|/).*\.pem$"
    r"|(^|/).*\.key$"
    r"|(^|/).*_rsa$"
    r"|(^|/).*_dsa$"
    r"|(^|/)\.aws/"
    r"|(^|/)\.ssh/"
    r"|(^|/)id_rsa"
    r"|(^|/)id_ed25519"
)


def _validate_ref(name: str) -> str | None:
    """Return an error message if ref name is unsafe, else None."""
    if not name:
        return "branch name is empty"
    if not _SAFE_REF.match(name):
        return f"branch name contains unsafe characters: {name!r}"
    if ".." in name or name.endswith(".lock"):
        return f"branch name is invalid: {name!r}"
    return None


def _run_git(
    args: list[str], cwd: str | None = None, timeout: int = 30
) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"git command timed out after {timeout}s"
    except FileNotFoundError:
        return -1, "", "git is not installed or not in PATH"
    except Exception as e:
        return -1, "", f"failed to run git: {e}"


def _format_result(returncode: int, stdout: str, stderr: str) -> str:
    """Format git output into a single result string."""
    parts: list[str] = []
    if stdout:
        text = stdout if len(stdout) <= MAX_OUTPUT else stdout[:MAX_OUTPUT] + "\n... (truncated)"
        parts.append(text)
    if stderr:
        text = stderr if len(stderr) <= MAX_OUTPUT else stderr[:MAX_OUTPUT] + "\n... (truncated)"
        parts.append(f"[stderr]\n{text}")
    body = "\n".join(parts) if parts else "(no output)"
    return f"[exit_code={returncode}]\n{body}"


def _check_sensitive_files(files: list[str]) -> list[str]:
    """Return list of sensitive file paths that should not be staged."""
    return [f for f in files if _SENSITIVE_PATTERNS.search(f)]


def _resolve_cwd(cwd: str | None) -> str:
    """Resolve working directory, default to current directory."""
    if cwd:
        if not os.path.isdir(cwd):
            return ""
        return cwd
    return os.getcwd()


async def execute(
    *,
    action: str,
    cwd: str | None = None,
    branch: str | None = None,
    message: str | None = None,
    files: list[str] | None = None,
    staged: bool = False,
    path: str | None = None,
) -> str:
    repo_dir = _resolve_cwd(cwd)
    if not repo_dir:
        return f"Error: working directory does not exist: {cwd}"

    # Verify we're in a git repo
    rc, _, _ = _run_git(["rev-parse", "--git-dir"], cwd=repo_dir)
    if rc != 0:
        return f"Error: {repo_dir} is not a git repository"

    if action == "status":
        rc, out, err = _run_git(["status", "--short", "--branch"], cwd=repo_dir)
        return _format_result(rc, out, err)

    elif action == "diff":
        args = ["diff"]
        if staged:
            args.append("--staged")
        args.append("--stat")
        rc_stat, out_stat, _ = _run_git(args, cwd=repo_dir)

        args_full = ["diff"]
        if staged:
            args_full.append("--staged")
        rc, out, err = _run_git(args_full, cwd=repo_dir)
        combined = f"{out_stat.rstrip()}\n\n{out}" if out_stat.strip() else out
        return _format_result(rc, combined, err)

    elif action == "branch_create":
        if not branch:
            return "Error: 'branch' is required for branch_create"
        err = _validate_ref(branch)
        if err:
            return f"Error: {err}"
        rc, out, err_msg = _run_git(["checkout", "-b", branch], cwd=repo_dir)
        return _format_result(rc, out, err_msg)

    elif action == "commit":
        if not message:
            return "Error: 'message' is required for commit"

        # Determine files to stage
        if files:
            # Check for sensitive files in explicit list
            sensitive = _check_sensitive_files(files)
            if sensitive:
                return (
                    f"Error: refusing to stage sensitive files: {', '.join(sensitive)}. "
                    f"Remove them from the files list or add them to .gitignore."
                )
            rc, out, err_msg = _run_git(["add", "--"] + files, cwd=repo_dir)
            if rc != 0:
                return _format_result(rc, out, err_msg)
        else:
            # Stage all tracked changes, but check for sensitive files first
            rc_diff, diff_out, _ = _run_git(
                ["diff", "--name-only", "--diff-filter=ACMR"], cwd=repo_dir
            )
            rc_untracked, untracked_out, _ = _run_git(
                ["ls-files", "--others", "--exclude-standard"], cwd=repo_dir
            )
            all_files = []
            if diff_out.strip():
                all_files.extend(diff_out.strip().splitlines())
            if untracked_out.strip():
                all_files.extend(untracked_out.strip().splitlines())

            sensitive = _check_sensitive_files(all_files)
            if sensitive:
                return (
                    f"Error: refusing to stage sensitive files: {', '.join(sensitive)}. "
                    f"Add them to .gitignore or specify files explicitly."
                )
            # Stage tracked modifications
            rc, out, err_msg = _run_git(["add", "-u"], cwd=repo_dir)
            if rc != 0:
                return _format_result(rc, out, err_msg)

        # Commit
        rc, out, err_msg = _run_git(["commit", "-m", message], cwd=repo_dir)
        return _format_result(rc, out, err_msg)

    elif action == "push":
        args = ["push"]
        if branch:
            err = _validate_ref(branch)
            if err:
                return f"Error: {err}"
            args.extend(["--set-upstream", "origin", branch])
        rc, out, err_msg = _run_git(args, cwd=repo_dir, timeout=60)
        return _format_result(rc, out, err_msg)

    elif action == "worktree_create":
        if not branch:
            return "Error: 'branch' is required for worktree_create"
        err = _validate_ref(branch)
        if err:
            return f"Error: {err}"

        # Keep the worktree inside the selected repository workspace so the
        # request-level path boundary also covers the new checkout.
        wt_base = os.path.join(repo_dir, ".agent-smith-worktrees")
        os.makedirs(wt_base, exist_ok=True)
        # Use branch name (sanitized) as directory name
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", branch)
        wt_path = os.path.join(wt_base, safe_name)

        if os.path.exists(wt_path):
            return f"Error: worktree path already exists: {wt_path}"

        rc, out, err_msg = _run_git(
            ["worktree", "add", wt_path, "-b", branch], cwd=repo_dir
        )
        if rc == 0:
            return f"OK: worktree created at {wt_path} on branch {branch}"
        return _format_result(rc, out, err_msg)

    elif action == "worktree_remove":
        if not path:
            return "Error: 'path' is required for worktree_remove"

        if not os.path.isdir(path):
            return f"Error: worktree path does not exist: {path}"

        rc, out, err_msg = _run_git(
            ["worktree", "remove", path, "--force"], cwd=repo_dir
        )
        return _format_result(rc, out, err_msg)

    elif action == "discover":
        sections: list[str] = []

        # Current branch
        rc, out, _ = _run_git(["branch", "--show-current"], cwd=repo_dir)
        if rc == 0:
            sections.append(f"Current branch: {out.strip()}")

        # All local branches
        rc, out, _ = _run_git(["branch", "--format=%(refname:short)"], cwd=repo_dir)
        if rc == 0 and out.strip():
            branches = out.strip().splitlines()
            sections.append(f"Local branches ({len(branches)}): {', '.join(branches)}")

        # Remotes
        rc, out, _ = _run_git(["remote", "-v"], cwd=repo_dir)
        if rc == 0 and out.strip():
            sections.append(f"Remotes:\n{out.strip()}")

        # Recent history (last 10 commits, oneline)
        rc, out, _ = _run_git(
            ["log", "--oneline", "-10", "--no-decorate"], cwd=repo_dir
        )
        if rc == 0 and out.strip():
            sections.append(f"Recent commits:\n{out.strip()}")

        # Dirty state
        rc, out, _ = _run_git(["status", "--short"], cwd=repo_dir)
        if rc == 0:
            if out.strip():
                sections.append(f"Working tree ({len(out.strip().splitlines())} changed files):\n{out.strip()}")
            else:
                sections.append("Working tree: clean")

        return "\n\n".join(sections) if sections else "Error: could not discover repo info"

    else:
        return f"Error: unknown action '{action}'. Use: status, diff, branch_create, commit, push, worktree_create, worktree_remove, discover"
