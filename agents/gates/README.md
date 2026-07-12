# Gates — pipeline 门禁内容层

门禁实现是**内容**,不是引擎代码。引擎 (`engine/execution/gate.py`) 只提供
`Gate` 接口、`GateResult`、`LLMGate` 包装器;具体的检查规则住在这里,按领域
分目录组织,由 `engine.execution.skill_chain.load_gate_content()` 启动时扫描注册。

## 目录约定

```
agents/gates/common/    跨领域通用门禁(understanding / planning / review …)
agents/gates/coding/    coding 领域门禁(test / rubric / pr / git_worktree …)
agents/gates/<domain>/  新领域按需添加,不改引擎
agents/conditions/      步骤条件(pipeline YAML 的 condition: 键)
```

## 编写一个门禁

任意 `.py` 文件(`_` 开头的除外),导出模块级 `GATES` 字典:

```python
from engine.execution.gate import GateResult

class MyGate:
    async def check(self, output: str, context: dict) -> GateResult:
        ok = "关键证据" in output
        return GateResult(
            "pass" if ok else "retry",
            "说明原因",
            retry_hint="不过时给 LLM 的重试提示",
        )

GATES = {"my_gate": MyGate}
```

- `GateResult.verdict`: `"pass"` 通过 / `"retry"` 同节点重试 / `"fail"` 走回退或阻断
- 需要 LLM 语义复核时用 `LLMGate(内层门禁, prompt 模板)` 包装,引擎会自动注入 gate LLM
- 条件文件同理,导出 `CONDITIONS = {"key": fn}`,`fn(ctx: dict) -> bool`

## pipeline YAML 引用

```yaml
base_gate: rubric        # 兜底层:每个节点产出先过它(可选,可为列表 base_gates)
steps:
  - skill: planning
    gate: planning_llm   # 领域层:该节点自己的门禁
    condition: needs_architecture   # 可选
```

键名冲突(两个文件注册同一 key)与内容文件语法错误都会在启动时直接抛错——
宁可启动失败,不许静默丢门禁。
