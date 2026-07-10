"""task_router 单测：上下文线索路由 + Evaluation-Sensitive 检测。"""

from engine.execution.task_router import (
    TaskType,
    detect_eval_sensitive,
    route_task,
)


def test_stack_trace_routes_bugfix_without_keywords():
    # Java 栈帧，无任何 bugfix 关键词
    msg = "看看这个:\nat com.example.Main(Main.java:10)"
    assert route_task(msg) == TaskType.BUGFIX


def test_python_traceback_routes_bugfix():
    msg = 'Traceback (most recent call last)\n  File "app.py", line 3\nValueError: bad'
    assert route_task(msg) == TaskType.BUGFIX


def test_user_story_routes_feature():
    msg = "作为用户，我希望能导出报表。验收标准：支持 CSV 格式。"
    assert route_task(msg) == TaskType.FEATURE


def test_context_clue_outweighs_single_keyword():
    # 1 个 feature 关键词（添加）+ 1 条 bug 上下文线索（栈帧，2 分）→ BUGFIX
    msg = "添加日志后还是崩:\nat com.example.Main(Main.java:10)"
    assert route_task(msg) == TaskType.BUGFIX


def test_plain_chat_routes_direct():
    assert route_task("今天天气怎么样") == TaskType.DIRECT


def test_exception_class_name_alone_is_weak_evidence():
    # 异常类名只经 error/exception 关键词计 1 分（不再作为上下文线索双重计分），
    # 不应压过明确的 feature 意图
    msg = "帮我实现一个表单校验功能，校验失败时抛 ValidationError"
    assert route_task(msg) != TaskType.BUGFIX


def test_eval_sensitive_positive():
    assert detect_eval_sensitive("跑一下 benchmark 看看分数")
    assert detect_eval_sensitive("让所有测试通过就行")
    assert detect_eval_sensitive("make the tests pass")
    assert detect_eval_sensitive("这题按评分标准判分")


def test_eval_sensitive_negative():
    assert not detect_eval_sensitive("帮我写个单元测试")
    assert not detect_eval_sensitive("今天天气怎么样")
    assert not detect_eval_sensitive("修一下登录页的 bug")


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
