"""platform-protect-001：pip/uv 安装只在涉及平台路径时拦截，用户项目内放行。"""
import sys
from pathlib import Path

from engine.safety.tool_guard import GuardResult, PermissionLevel, ToolGuard
from engine.safety.tool_policy import ToolPolicy
from engine.tool.interface import ToolCall, ToolDefinition

_RULES = Path(__file__).resolve().parents[2] / "agents" / "safety" / "dangerous_commands.json"


def _check(command):
    return ToolGuard(_RULES).check(ToolCall(id="t", name="shell", arguments={"command": command}))


def _check_tool(name, arguments):
    return ToolGuard(_RULES).check(ToolCall(id="t", name=name, arguments=arguments))


class _FakeGuard:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def check(self, call):
        self.calls.append(call)
        return self.result


def test_tool_policy_allows_without_guard():
    decision = ToolPolicy().evaluate(ToolCall(id="t", name="read_file", arguments={}))

    assert decision.allowed
    assert decision.observation == ""


def test_tool_policy_maps_guard_block_to_observation():
    guard = _FakeGuard(
        GuardResult(
            allowed=False,
            reason="needs approval",
            level=PermissionLevel.DESTRUCTIVE,
            needs_confirmation=True,
        )
    )
    call = ToolCall(id="t", name="shell", arguments={"command": "rm -rf ./x"})

    decision = ToolPolicy(guard).evaluate(call)

    assert guard.calls == [call]
    assert not decision.allowed
    assert decision.reason == "needs approval"
    assert decision.level is PermissionLevel.DESTRUCTIVE
    assert decision.needs_confirmation
    assert decision.observation == "[BLOCKED] needs approval"


def test_pip_install_in_user_project_allowed():
    assert _check("pip install requests").allowed


def test_pip_install_into_platform_blocked():
    assert not _check("pip install --target ~/Downloads/Agent-Smith/engine requests").allowed


def test_pip_install_with_platform_path_before_blocked():
    # 平台路径出现在 pip install 之前也要拦（lookahead 与顺序无关）
    assert not _check("PIP_TARGET=~/Downloads/Agent-Smith/vendor pip install requests").allowed


def test_uv_add_in_user_project_allowed():
    assert _check("uv add httpx").allowed


def test_rm_platform_data_blocked():
    assert not _check("rm -rf ~/.agent-smith/agent").allowed


def test_path_tools_are_guarded():
    blocked_calls = [
        ("grep", {"pattern": "root", "path": "/etc"}),
        ("glob_files", {"pattern": "*.conf", "path": "/etc"}),
        ("list_dir", {"path": "/etc"}),
        ("edit_file", {"path": "/etc/hosts", "old_string": "a", "new_string": "b"}),
        ("git_ops", {"action": "worktree_remove", "path": "/etc"}),
        ("git_ops", {"action": "commit", "cwd": str(Path.cwd()), "files": ["/etc/passwd"]}),
        ("shell", {"command": "pwd", "cwd": "/etc"}),
    ]
    for name, arguments in blocked_calls:
        assert not _check_tool(name, arguments).allowed, name


def test_web_tool_aliases_keep_read_permission_level():
    assert _check_tool("websearch", {"query": "docs"}).level is PermissionLevel.READ
    assert _check_tool("webfetch", {"url": "https://example.com"}).level is PermissionLevel.READ


def test_metadata_declared_path_args_are_guarded_without_hardcoded_entry():
    # custom_writer is absent from ToolGuard's fallback tables — checks must
    # come purely from the declared ToolDefinition metadata.
    defn = ToolDefinition(
        name="custom_writer",
        description="",
        path_args=("target",),
        is_write_tool=True,
    )
    guard = ToolGuard(_RULES, tool_registry={"custom_writer": defn})

    outside = guard.check(
        ToolCall(id="t", name="custom_writer", arguments={"target": "/etc/hosts"})
    )
    assert not outside.allowed

    env_write = guard.check(
        ToolCall(
            id="t",
            name="custom_writer",
            arguments={"target": str(Path.home() / "proj" / ".env")},
        )
    )
    assert not env_write.allowed
    assert env_write.needs_confirmation


def test_metadata_permission_level_overrides_fallback():
    defn = ToolDefinition(name="notes_read", description="", permission_level="read")
    guard = ToolGuard(_RULES, tool_registry={"notes_read": defn})

    assert guard.check(ToolCall(id="t", name="notes_read", arguments={})).level is PermissionLevel.READ
    # Without metadata an unknown tool stays at the EXECUTE default.
    assert ToolGuard(_RULES).check(ToolCall(id="t", name="notes_read", arguments={})).level is PermissionLevel.EXECUTE


def test_session_whitelist_extends_boundary_but_not_sensitive_blocks():
    guard = ToolGuard(_RULES)
    call = ToolCall(id="t", name="list_dir", arguments={"path": "/opt/data/project"})

    assert not guard.check(call).allowed

    guard.whitelist.allow_path("/opt/data")
    assert guard.check(call).allowed

    # Sensitive paths stay blocked even when whitelisted.
    ssh_path = str(Path.home() / ".ssh")
    guard.whitelist.allow_path(ssh_path)
    assert not guard.check(ToolCall(id="t", name="list_dir", arguments={"path": ssh_path})).allowed


def test_dollar_anchored_rule_patterns_match_raw_argument_values():
    home = Path.home()

    pem = _check_tool("read_file", {"path": str(home / "certs" / "server.pem")})
    assert not pem.allowed
    assert "sens-file-004" in pem.reason

    env = _check_tool("read_file", {"path": str(home / "proj" / ".env")})
    assert not env.allowed
    assert "sens-file-003" in env.reason

    # Exclude patterns still apply — .env.example stays readable.
    assert _check_tool("read_file", {"path": str(home / "proj" / ".env.example")}).allowed


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failures else 0)
