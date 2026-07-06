"""platform-protect-001：pip/uv 安装只在涉及平台路径时拦截，用户项目内放行。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safety.tool_guard import ToolGuard  # noqa: E402
from tool.interface import ToolCall  # noqa: E402

_RULES = Path(__file__).resolve().parents[2] / "agents" / "safety" / "dangerous_commands.json"


def _check(command):
    return ToolGuard(_RULES).check(ToolCall(id="t", name="shell", arguments={"command": command}))


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
    assert not _check("rm -rf ~/.agent-smith/employees").allowed


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
