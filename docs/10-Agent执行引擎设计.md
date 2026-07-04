# 10 · Agent 执行引擎设计

> 2026-07-04。基于 QoderWake 逆向分析，定义 Agent-Smith engine/ 的执行模型。

## 一、总体结构：四层嵌套

```
第 1 层：任务入口（路由决策）          ← 代码控制，规则引擎
    ↓
第 2 层：技能链编排（DAG 流转）        ← 代码控制，有向图
    ↓
第 3 层：单技能执行（ReAct 循环）      ← LLM 控制，灵活
    ↓
第 4 层：工具调用（安全护栏过滤）      ← 代码控制，正则拦截
```

宏观流程由代码确定性控制（第 1、2、4 层），LLM 只在第 3 层获得自由度。

## 二、第 1 层 — 任务路由

对应文件：`engine/execution/task_router.py`

```
收到任务
  │
  ├── 规则匹配
  │     ├── 关键词：fix / bug / error / broken → Bug Fix
  │     ├── 关键词：feature / add / implement / 新增 → Feature
  │     ├── 上下文：包含 stack trace / error log → Bug Fix
  │     ├── 上下文：包含需求描述 / 设计稿 → Feature
  │     └── 用户显式指定（@bugfix / @feature / @direct）
  │
  └── 路由结果
        ├── Bug Fix   → 走 Bug Fix 技能链
        ├── Feature   → 走 Feature 技能链
        └── Direct    → 跳过技能链，直接进 ReAct 循环
```

设计要点：

- 规则引擎，不是 LLM prompt。快、确定、可审计
- Direct 路由处理简单问答、解释代码等不需要完整工作流的任务
- 路由结果可被用户覆盖（显式指定优先于规则匹配）

## 三、第 2 层 — 强制技能链（DAG）

对应文件：`engine/execution/skill_chain.py`

### 3.1 技能链定义

```
Feature 路由：
  planning → architecture(条件:3+文件/跨模块) → testing-strategy → change-validation → code-review

Bug Fix 路由：
  sde-debug → planning → testing-strategy → change-validation → code-review

Direct 路由：
  无技能链，直接进入 agent_loop 的 ReAct 循环
```

### 3.2 硬规则

- Bug Fix 路由必须使用 sde-debug 和 testing-strategy，不可替代
- Feature 路由中 architecture 仅在变更涉及 3+ 文件或跨模块时触发
- code-review 始终是最后一步，不可跳过
- 每个技能节点都有独立的门禁，必须通过才能进入下一步

### 3.3 数据结构

```python
chain = SkillChain(
    nodes=[
        SkillNode("planning", gate=PlanningGate()),
        SkillNode("architecture", gate=DesignGate(), condition=lambda ctx: ctx.files_changed >= 3),
        SkillNode("testing-strategy", gate=TestGate()),
        SkillNode("change-validation", gate=ValidationGate()),
        SkillNode("code-review", gate=ReviewGate()),
    ],
    backtrack_map={
        "change-validation": "planning",
        "code-review": "change-validation",
    }
)
```

## 四、第 3 层 — 单技能执行（ReAct）

对应文件：`engine/execution/agent_loop.py`

```
加载 SKILL.md 指令到 prompt
    ↓
ReAct 循环：思考 → 调工具 → 观察 → 思考 → ... → 生成输出
    ↓
输出结果交给门禁检查
```

### 4.1 核心逻辑

```python
async def react_loop(llm, messages, tools, max_iters=20):
    for i in range(max_iters):
        response = await llm.chat(messages, tools=tools)

        if response.has_tool_calls:
            for call in response.tool_calls:
                guard_result = tool_guard.check(call)
                if guard_result.blocked:
                    messages.append(tool_result(call.id, f"[BLOCKED] {guard_result.reason}"))
                    continue
                result = await tool_registry.execute(call)
                messages.append(tool_result(call.id, result))
        else:
            return response.text

    return "[max iterations reached]"
```

### 4.2 自主执行策略

默认做了再说，不问用户。只在两种情况停下来：

1. 契约关键阻断 — 需求有多种互斥解读，无法自行判断
2. 高风险不可逆 — 删除数据、force push、修改生产配置

明确禁止的反模式：

- "要我继续吗？" → 默认继续
- "要我创建文件吗？" → 直接创建
- "要我运行测试吗？" → 直接运行

## 五、第 4 层 — 工具安全护栏

对应文件：`engine/safety/tool_guard.py` + `agents/safety/dangerous_commands.json`

```
LLM 生成 tool_call
    ↓
tool_guard 正则匹配规则库
    ├── 命中 → 拦截 / 降级 / 要求确认
    └── 未命中 → 继续
    ↓
file_guard 检查路径白名单
    ├── 目录外 → 拦截
    └── 目录内 → 放行
    ↓
执行工具，返回结果
```

### 5.1 七大类安全规则

| 类别 | 说明 | 示例 |
|---|---|---|
| command_injection | 防注入 | 管道拼接、反引号执行 |
| resource_abuse | 防资源滥用 | fork 炸弹、无限循环 |
| code_execution | 防任意执行 | eval、exec、动态 import |
| network_abuse | 防网络滥用 | 数据外传、反向 shell |
| sensitive_file_access | 防敏感文件 | /etc/passwd、~/.ssh/、.env |
| privilege_escalation | 防权限提升 | sudo、chmod 777 |
| shell_evasion | 防绕过 | 编码绕过、history 篡改 |

### 5.2 规则格式

```json
{
  "id": "rule-001",
  "tools": ["shell"],
  "category": "command_injection",
  "severity": "critical",
  "patterns": ["正则表达式数组"],
  "excludePatterns": ["排除模式数组"],
  "description": "规则描述",
  "remediation": "修复建议"
}
```

## 六、贯穿机制 — 门禁系统

对应文件：`engine/execution/gate.py`

### 6.1 门禁清单

| 门禁 | 位置 | 通过条件 | 失败处理 |
|---|---|---|---|
| Understanding Gate | 理解阶段末 | 能准确复述需求 + 识别边界 | 回退重新理解 |
| Root Cause Gate | 调试阶段末 | 有证据支持的根因 | 回退到 Reproduce |
| Planning Gate | 规划阶段末 | 步骤完整 + 有验证点 | 重新规划 |
| Contract Alignment Gate | 实现前 | 方案与契约一致 | 回退到 Planning |
| Test Gate | 测试策略末 | 测试覆盖关键路径 + 边界 | 补充测试 |
| Validation Gate | 验证阶段末 | 测试通过 + 无回归 | 回退到 Planning |
| Review Gate | Code Review 末 | 无 P0/P1 问题 | 修复后重新 Review |
| Skill Rubric Gate | 每个技能后 | 输出满足质量标准 | 最多重试 2 次 |
| Metadata Safety Gate | 全程 | 无敏感信息泄露 | 阻断并告警 |

### 6.2 Skill Rubric Gate 重试策略

```
技能执行完成
  │
  ├── 检查输出质量
  │     ├── 通过 → DAG 前进到下一个节点
  │     └── 未通过
  │           ├── 第 1 次：调整参数/上下文重执行
  │           ├── 第 2 次：换策略执行
  │           └── 第 3 次：标记 blocked
```

### 6.3 门禁实现模式

```python
class Gate(Protocol):
    async def check(self, skill_output: str, context: TaskContext) -> GateResult: ...

@dataclass
class GateResult:
    verdict: Literal["pass", "fail", "retry"]
    reason: str
    retry_hint: str | None = None
```

门禁检查可以是：
- 规则检查（输出里是否包含必要结构）
- LLM 自评（让 LLM 评估自己的输出质量）
- 工具验证（运行测试、检查编译）

## 七、贯穿机制 — 回退 + Failure Loop Guard

对应文件：`engine/execution/backtrack.py`

### 7.1 回退路径

```
Implementation 失败 → 回退到 Planning
Design 失败       → 回退到 Understand
RootCause 失败    → 回退到 Reproduce
Verify 失败       → 回退到 Planning
```

回退不是简单重试，而是回到上游节点重新执行，带上失败原因作为额外上下文。

### 7.2 Failure Loop Guard

```
任何失败发生
    ↓
记录失败签名 = hash(错误类型 + 上下文摘要)
    ↓
同一签名出现过几次？
    ├── 第 1 次 → 常规处理
    ├── 第 2 次（同签名）→ 换策略（最多 2 种替代）
    └── 所有策略失败 → 声明 blocked，请求人工介入
```

关键：不是限制重试次数，而是识别"用同样方式犯同样错误"。

### 7.3 实现要点

```python
@dataclass
class FailureSignature:
    error_type: str
    context_hash: str

class FailureLoopGuard:
    def __init__(self, max_same_failure=2, max_strategies=2):
        self.seen: dict[FailureSignature, int] = {}
        self.strategy_index: int = 0

    def record_failure(self, sig: FailureSignature) -> Action:
        self.seen[sig] = self.seen.get(sig, 0) + 1
        if self.seen[sig] < self.max_same_failure:
            return Action.RETRY
        if self.strategy_index < self.max_strategies:
            self.strategy_index += 1
            return Action.SWITCH_STRATEGY
        return Action.BLOCKED
```

## 八、System Prompt 8 层组装

对应文件：`engine/prompt/assembler.py`

| 层 | 来源 | 职责 |
|---|---|---|
| 1 | role.md | 核心使命（最高优先级） |
| 2 | style.md | 行为风格 |
| 3 | workflow.md | 工作流 SOP + 门禁定义 |
| 4 | toolbox.md + 工具注册表 | 可用工具 + 使用规范 |
| 5 | 技能注册表 | 可用技能 + 使用策略 |
| 6 | context.md | 用户偏好（自动学习） |
| 7 | memory/ 索引 | 记忆摘要 |
| 8 | 运行时上下文 | 员工 ID / 会话 ID / 环境 |

组装规则：
- 层 1-3 从员工目录读取
- 层 4-5 动态生成
- 层 6-7 从员工目录读取
- 层 8 运行时注入

## 九、完整执行流程示例

用户给前端工程师员工发消息："帮我修复登录页的表单验证 bug"

```
1. [task_router] 关键词"修复""bug" → Bug Fix 路由

2. [skill_chain] 加载 Bug Fix 技能链：
   sde-debug → planning → testing-strategy → change-validation → code-review

3. [sde-debug] ReAct 循环 → 根因分析 → Root Cause Gate 通过
4. [planning] ReAct 循环 → 修复计划 → Planning Gate 通过
5. [testing-strategy] ReAct 循环 → 测试策略 → Test Gate 通过
6. [change-validation] ReAct 循环 → 执行修复 + 运行测试
   → Validation Gate 失败 → backtrack 到 planning
   → Failure Loop Guard: 第 1 次，常规回退
   → 重新 planning → 重新 validation → 通过
7. [code-review] ReAct 循环 → 自审 → Review Gate 通过

8. 输出最终结果给用户
```

## 十、文件映射总览

```
engine/
├── llm/
│   ├── client.py               ← LLM API + 流式 + tool_call 解析
│   └── model_config.py         ← 从 config_loader 获取 LLM 配置
├── prompt/
│   ├── assembler.py            ← 8 层 System Prompt 组装
│   └── placeholder.py          ← 占位符渲染
├── tool/
│   ├── interface.py            ← ToolProvider 协议
│   ├── registry.py             ← 工具注册 + 发现 + build_tools(context)
│   └── schema.py               ← 函数签名 → JSON Schema
├── skill/
│   ├── loader.py               ← SKILL.md 解析
│   ├── registry.py             ← 技能注册（内置 / 自装）
│   └── executor.py             ← 技能执行
├── execution/
│   ├── task_router.py          ← 第 1 层：任务路由（规则引擎）
│   ├── skill_chain.py          ← 第 2 层：技能链 DAG
│   ├── agent_loop.py           ← 第 3 层：ReAct 循环
│   ├── gate.py                 ← 门禁系统
│   └── backtrack.py            ← 回退 + Failure Loop Guard
├── memory/
│   ├── interface.py            ← 记忆协议
│   ├── store.py                ← 记忆读写
│   ├── dream.py                ← Dream 整理
│   └── user_learner.py         ← USER.md 自动填充
└── safety/
    ├── guard_rules.py          ← 规则加载
    └── tool_guard.py           ← 工具调用前置拦截
```
