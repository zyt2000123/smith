# Agent 执行引擎设计文档

## 设计哲学

> **宏观确定性控制，微观 LLM 自由度** —— 代码管流程，LLM 只在 ReAct 循环里有自由度。

Agent-Smith 的执行引擎采用"硬骨架 + 软肌肉"架构：

- **硬骨架**（代码控制）：任务路由、技能链 DAG 推进、门禁判定、回退策略、安全护栏 —— 全部由确定性的 Python 逻辑驱动，不给 LLM 任何绕过空间。
- **软肌肉**（LLM 自由度）：仅在 ReAct 循环内部，LLM 决定调什么工具、传什么参数、如何整合观察结果。这是它唯一拥有自主权的层面。

这个哲学来自一个关键洞察：LLM 擅长局部推理和工具使用，但不擅长长链执行的自我管理。把"流程推进"交给代码、"步骤执行"交给 LLM，二者各司其职。

---

## 四层嵌套执行模型

```
┌───────────────────────────────────────────────────┐
│  第1层  任务路由 (task_router.py)                    │  纯规则，不用 LLM
│  route_task("帮我修复登录bug")  →  TaskType.BUGFIX  │
├───────────────────────────────────────────────────┤
│  第2层  技能链 DAG (skill_chain.py)                  │  确定性编排
│  sde-debug → planning → testing → validation → review │
├───────────────────────────────────────────────────┤
│  第3层  ReAct 循环 (agent_loop.py)                   │  LLM 自由度区间
│  think → tool_call → 安全检查 → execute → observe    │
├───────────────────────────────────────────────────┤
│  第4层  安全护栏 (tool_guard.py)                     │  每次工具调用前拦截
│  正则匹配 → 放行/阻断                                │
└───────────────────────────────────────────────────┘
```

控制权从上到下层层递进：第 1 层决定走哪条流水线，第 2 层决定节点顺序和回退，第 3 层让 LLM 在单节点内自由执行，第 4 层在每次工具调用前做最后的安全拦截。

---

### 第 1 层：任务路由

**文件**: `engine/execution/task_router.py`

任务路由是最外层的分发逻辑。它是一个纯规则引擎 —— 不调 LLM、不做 embedding、不查知识库。

#### TaskType 枚举

```python
class TaskType(Enum):
    BUGFIX  = "bugfix"   # 修复类任务 → bugfix_chain
    FEATURE = "feature"  # 功能开发 → feature_chain
    DIRECT  = "direct"   # 简单对话 → 直接 ReAct
```

#### 关键词表

| 类别 | 数量 | 示例 |
|---|---|---|
| Bug Fix 关键词 | 19 个 | `bug`, `fix`, `error`, `crash`, `broken`, `issue`, `debug`, `traceback`, `exception`, `fail`, `regression`, `wrong`, `修复`, `修改`, `报错`, `异常`, `崩溃`, `出错`, `排查` |
| Feature 关键词 | 18 个 | `add`, `create`, `build`, `implement`, `new feature`, `design`, `develop`, `integrate`, `support`, `enable`, `新增`, `实现`, `开发`, `创建`, `添加`, `搭建`, `接入`, `支持` |

#### route_task() 算法

```python
def route_task(user_message: str) -> TaskType:
    lower = user_message.lower()
    bug_score  = sum(1 for kw in _BUGFIX_KEYWORDS  if kw in lower)
    feat_score = sum(1 for kw in _FEATURE_KEYWORDS if kw in lower)

    if bug_score > feat_score and bug_score > 0:
        return TaskType.BUGFIX
    if feat_score > bug_score and feat_score > 0:
        return TaskType.FEATURE
    return TaskType.DIRECT  # 平局或全部为零
```

决策逻辑：

1. 将用户消息全部转小写
2. 分别计算 Bug Fix / Feature 关键词命中数
3. 取高分方，严格大于（不是 `>=`）
4. 平局或零命中 → `DIRECT`（不走技能链，直接 ReAct）

**设计取舍**：选择关键词匹配而非 LLM 分类，是因为路由本身不需要理解语义，只需要一个足够好的"初筛"。错分的代价很低 —— DIRECT 模式仍然能完成任务，只是缺少结构化流程。

---

### 第 2 层：技能链 DAG

**文件**: `engine/execution/skill_chain.py`

技能链定义了技能节点的执行顺序、门禁要求和回退策略。

#### 核心数据结构

```python
@dataclass
class SkillNode:
    skill_name: str                              # 技能名
    gate: Gate                                   # 通过条件
    condition: Callable[[dict], bool] | None = None  # 跳过条件（返回 False 时跳过）

class SkillChain:
    nodes: list[SkillNode]                       # 有序节点列表
    backtrack_map: dict[str, str]                # 失败时回退映射
```

#### Feature 链（功能开发）

```
planning ──→ architecture ──→ testing-strategy ──→ change-validation ──→ code-review
  PlanningGate   DesignGate      TestGate           ValidationGate        ReviewGate
               (条件跳过:                   
                <3文件时跳过)
```

**architecture 条件判断**：

```python
def _needs_architecture(ctx: dict) -> bool:
    plan_output = ctx.get("planning_output", "")
    file_refs = re.findall(r'[\w/]+\.\w{1,5}', plan_output)
    return len(set(file_refs)) >= 3  # 3+ 不同文件才需要架构设计
```

逻辑：从 planning 阶段的输出中正则提取文件路径引用，去重后如果少于 3 个文件，说明是小改动，跳过架构设计环节。

#### Bug Fix 链（修复任务）

```
sde-debug ──→ planning ──→ testing-strategy ──→ change-validation ──→ code-review
 RootCauseGate  PlanningGate    TestGate          ValidationGate        ReviewGate
```

**关键区别**：Bug Fix 链首节点是 `sde-debug`（根因分析），配 `RootCauseGate`。要求 LLM 必须先定位根因并给出证据，才能进入修复规划。

#### 回退映射

两条链共享同一套回退规则：

| 失败节点 | 回退目标 |
|---|---|
| `change-validation` | → `planning` |
| `code-review` | → `change-validation` |
| `testing-strategy` | → `planning` |

含义：如果代码验证失败，回退到规划阶段重新设计方案；如果代码评审失败，回退到验证阶段重新验证；如果测试策略不合格，回退到规划。

#### 硬规则

1. **Bug Fix 必须从 `sde-debug` 开始** —— 没有根因就不能修
2. **`architecture` 仅大变更触发** —— 少于 3 文件的改动自动跳过
3. **`code-review` 不可跳过** —— 没有 `condition` 字段，永远执行

---

### 第 3 层：ReAct 循环

**文件**: `engine/execution/agent_loop.py`

这是 LLM 唯一拥有自由度的层面。

#### _react_loop()

标准的 Think → Act → Observe 循环：

```python
async def _react_loop(
    llm: LLMClient,
    messages: list[dict],
    tool_registry: ToolRegistry,
    tool_guard: ToolGuard | None = None,
    max_iters: int = 20,
) -> str:
```

每轮迭代：
1. 调 LLM，附带所有可用工具的 schema
2. 如果 LLM 没有返回 `tool_calls` → 返回文本（结束）
3. 如果有 `tool_calls` → 对每个调用：
   - 先过 `ToolGuard` 安全检查
   - 被阻断 → 返回 `[BLOCKED] {reason}` 给 LLM（LLM 看到后会换方案）
   - 放行 → 执行工具，将结果拼入对话
4. 继续下一轮迭代

**最大迭代次数**：20 次。达到上限返回 `"Max ReAct iterations reached."`。

#### _react_stream_loop()

流式变体。与 `_react_loop` 的区别：

- 工具调用阶段完全同步（跟非流式一致）
- 最终回复（无 tool_calls 的那一轮）通过 `llm.chat_stream()` 重新发起，逐 chunk yield
- 用于 SSE 推送到前端

#### run_agent()

顶层编排器，连接路由结果与执行模式：

```python
async def run_agent(
    llm, system_prompt, user_message,
    tool_registry, skill_registry,
    task_type, skill_chain, guard,
    tool_guard=None, max_react_iters=20,
) -> str:
```

**DIRECT 模式**：

```python
if task_type == TaskType.DIRECT or skill_chain is None:
    return await _react_loop(llm, base_messages, tool_registry, tool_guard, max_react_iters)
```

直接走一个 ReAct 循环，不经过任何技能链。

**BUGFIX / FEATURE 模式**（技能链执行）：

对技能链中的每个节点，执行以下流程：

```
┌─ 节点 N ─────────────────────────────────────────┐
│                                                    │
│  1. 检查 condition → 不满足则跳过                    │
│                                                    │
│  2. Rubric Gate 重试循环 (最多 3 次)                 │
│     ├─ 有 SKILL.md → execute_skill()               │
│     └─ 无 SKILL.md → _react_loop() + 技能名提示      │
│     ├─ 第 1 次重试: 带 rubric feedback hint          │
│     └─ 第 2 次重试: "Switch strategy" 指令           │
│     → SkillRubricGate.check() → pass/retry          │
│                                                    │
│  3. 通过 Rubric 后 → 节点专属 Gate                   │
│     → pass → 存输出, 进入下一节点                     │
│     → fail → FailureLoopGuard.record()              │
│       ├─ "retry"  → 留在当前节点                     │
│       ├─ "switch" → 按 backtrack_map 回退            │
│       └─ "blocked" → 终止, 返回错误                  │
│                                                    │
│  全局上限: 最多 5 次回退                              │
└────────────────────────────────────────────────────┘
```

#### reply() 和 reply_stream()

服务器层入口点，完成从配置到执行到善后的全链路：

```
reply(employee_id, name, user_message)
  │
  ├─ 加载 LLM 配置 (resolve_llm_config → build_llm_client)
  ├─ 初始化 ToolRegistry (从 agents/tools/ 加载 provider)
  ├─ 初始化 SkillRegistry (内置 agents/skills/ + Agent skills/)
  ├─ 组装 System Prompt (PromptAssembler.assemble)
  ├─ 路由任务 (route_task → TaskType)
  ├─ 构建技能链 (feature_chain / bugfix_chain / None)
  ├─ 初始化 FailureLoopGuard + ToolGuard
  ├─ 执行 (run_agent)
  ├─ 保存对话记忆 (save_conversation_memory, 仅工具调用时)
  └─ 学习用户偏好 (UserPreferenceLearner.observe)
```

`reply_stream()` 是流式变体：

- DIRECT 任务使用 `_react_stream_loop`（真正流式）
- BUGFIX/FEATURE 任务回退到非流式 `run_agent`，一次性 yield 全部结果

**自主执行策略**：默认做了再说（Act-first）。LLM 在 ReAct 循环内自主决定工具调用，只在需求存在互斥解读或高风险不可逆操作时才应停下请求确认。这个策略通过 prompt 层面引导，不在代码层面强制。

---

### 第 4 层：安全护栏

**文件**: `engine/safety/tool_guard.py`

每次工具调用在实际执行前，都必须先过 ToolGuard 的正则检查。

#### 核心数据结构

```python
@dataclass
class GuardResult:
    allowed: bool
    reason: str = ""

class ToolGuard:
    def __init__(self, rules_path: Path) -> None:
        # 从 JSON 文件加载规则
        self._rules: list[dict] = json.loads(rules_path.read_text())

    def check(self, tool_call: ToolCall) -> GuardResult:
        args_str = json.dumps(tool_call.arguments)
        # 遍历每条规则，逐一匹配
```

#### 检查流程

```
tool_call 到达
  │
  ├─ 序列化 arguments 为 JSON 字符串
  ├─ 遍历所有规则:
  │   ├─ 工具类型过滤 (tools 字段)
  │   ├─ 正则匹配 (patterns 数组)
  │   ├─ 排除模式检查 (excludePatterns)
  │   └─ 命中且未排除 → 返回 GuardResult(allowed=False)
  └─ 全部通过 → 返回 GuardResult(allowed=True)
```

#### 规则文件

**文件**: `agents/safety/dangerous_commands.json`

7 大类 24 条规则：

| 类别 | 规则数 | 严重度 | 示例规则 |
|---|---|---|---|
| `command_injection` | 4 | critical | 管道注入 shell (`\| bash`)、`$()` 命令替换、`eval` 执行、变量扩展注入 |
| `resource_abuse` | 3 | critical/major | Fork bomb、无退出条件的死循环、创建超大文件 |
| `code_execution` | 4 | critical | `python -c eval/exec`、`__import__()` 动态导入、`compile()` 动态编译、`node -e` 内联执行 |
| `network_abuse` | 3 | critical/major | 外部 POST 数据泄露、反向 shell、端口扫描 |
| `sensitive_file_access` | 4 | critical/major | `/etc/passwd`+`/etc/shadow`、SSH 密钥、`.env` 文件、私钥文件 |
| `privilege_escalation` | 3 | critical | `sudo`/`su` 提权、`chmod 777` 全局可写、`setuid`/`setgid` 位 |
| `shell_evasion` | 3 | critical/major | Base64 解码管道执行、清除 shell 历史、覆盖标准命令别名 |

每条规则结构：

```json
{
  "id": "cmd-inj-001",
  "tools": ["shell"],
  "category": "command_injection",
  "severity": "critical",
  "patterns": ["\\|\\s*(bash|sh|zsh|dash)"],
  "excludePatterns": ["\\|\\s*grep", "\\|\\s*sort"],
  "description": "Pipe output to shell interpreter",
  "remediation": "Use specific commands instead of piping to a shell."
}
```

`excludePatterns` 的作用：避免误伤。比如 `| grep` 是安全的管道用法，不应该被 `| bash` 规则误拦。

---

## 门禁系统

**文件**: `engine/execution/gate.py`

门禁是技能链的质量检查点。每个技能节点执行完后，输出必须通过门禁才能进入下一个节点。

### Gate 协议

```python
class Gate(Protocol):
    async def check(self, output: str, context: dict) -> GateResult

@dataclass
class GateResult:
    verdict: Literal["pass", "fail", "retry"]
    reason: str
    retry_hint: str | None = None
```

三种判定：
- `pass` — 通过，进入下一节点
- `retry` — 不合格但可以重试，附带 `retry_hint` 告诉 LLM 如何改进
- `fail` — 硬性失败，通常触发回退

### 10 个门禁实现

| 门禁 | 绑定节点 | 检查内容 | 通过条件 |
|---|---|---|---|
| **PlanningGate** | `planning` | 编号步骤 + 验证关键词 | >= 3 步 (`^\s*\d+[.、)]`) + 含"验证/检查/verify/check/test" |
| **TestGate** | `testing-strategy` | 测试用例 + 边界覆盖 | >= 2 测试模式 + 含"边界/edge/boundary/corner/negative" |
| **ValidationGate** | `change-validation` | 执行证据 + 结果 | 含执行关键词 + pass/fail 数字计数 |
| **ReviewGate** | `code-review` | 分级 + 可操作发现 | P0/P1/P2 分级 + 具体 finding 或显式"no issues" |
| **RootCauseGate** | `sde-debug` | 根因声明 + 证据 | 含"根因/root cause/caused by" + 含"证据/evidence/log/trace" |
| **SkillRubricGate** | 所有节点(通用) | 基本质量 | 长度>50 字符 + 有代码块或文件引用 + 无`[ERROR]`/`failed`/`unable to` |
| **DesignGate** | `architecture` | 结构完整性 | 含涉及文件 + 含数据流描述 + 含依赖关系 |
| **GitWorktreeGate** | (扩展用) | worktree 状态 | 有 worktree 设置证据 + 无冲突 + 状态干净 |
| **PRGate** | (扩展用) | 提交规范 + 敏感文件 | Conventional Commit 格式 + 无 `.env`/credentials/`.pem` 等禁止文件 |
| **TestDeliveryGate** | (扩展用) | 测试执行证据 | 有测试运行命令 + 有 pass/fail 计数 |

### 双层门禁机制

每个技能节点实际要过两道门禁：

```
技能输出
  │
  ├─ 第1道: SkillRubricGate (通用质量门禁)
  │   检查: 长度>50 + 有代码/文件引用 + 无错误标记
  │   └─ 不通过 → 重试 (最多3次)
  │       ├─ 第1次重试: 带 rubric feedback hint
  │       └─ 第2次重试: "Switch strategy" 换策略
  │
  └─ 第2道: 节点专属 Gate (PlanningGate / TestGate / ...)
      检查: 该节点特定的质量标准
      └─ 不通过 → FailureLoopGuard 决策
```

设计考量：SkillRubricGate 挡掉明显的低质量输出（太短、无实质内容、包含错误），避免节点专属 Gate 在垃圾输出上浪费判断。

### 重试策略

Rubric Gate 重试（3 次）：

| 次数 | 策略 |
|---|---|
| 第 1 次 | 原始执行 |
| 第 2 次 | 带 `retry_hint` 重新执行，告诉 LLM 哪里不达标 |
| 第 3 次 | 发送 "Switch strategy: try a completely different approach" |
| 超出 | 返回 `Blocked: skill '{name}' failed rubric gate after 3 attempts` |

节点专属 Gate 重试由 `FailureLoopGuard` 控制（见下节）。

---

## 回退 + Failure Loop Guard

**文件**: `engine/execution/backtrack.py`

### 核心洞察

> 不是限制重试次数，而是识别"用同样方式犯同样错误"。

传统的重试限制（"最多重试 3 次"）有一个问题：LLM 可能每次都用相同的错误策略重试，浪费算力。FailureLoopGuard 的设计目标是检测这种模式并强制换方向。

### 数据结构

```python
@dataclass
class FailureSignature:
    error_type: str       # 通常是 skill_name
    context_hash: str     # 输出内容的 MD5 前8位

class FailureLoopGuard:
    max_same: int = 2          # 同一错误签名最多出现 2 次
    max_strategies: int = 2     # 最多尝试 2 种不同策略
```

### record() 决策逻辑

```python
def record(self, sig: FailureSignature) -> Literal["retry", "switch", "blocked"]:
    key = f"{sig.error_type}:{sig.context_hash}"
    self._counts[key] = self._counts.get(key, 0) + 1
    self._strategies_tried.add(sig.error_type)

    if self._counts[key] < self.max_same:
        return "retry"       # 同一错误还没到上限，再试一次

    if len(self._strategies_tried) >= self.max_strategies:
        return "blocked"     # 已经换过策略了，还是失败 → 彻底阻断

    return "switch"          # 同一错误重复太多次 → 要求换策略（回退）
```

状态机：

```
首次失败 → "retry" (留在当前节点)
同一错误第2次 → "switch" (按 backtrack_map 回退)
回退后换了策略仍然失败且策略数≥2 → "blocked" (终止)
```

`context_hash` 的作用：对输出内容做 MD5，用于区分"完全相同的失败"和"不同的失败"。如果 LLM 换了一种方式但还是失败在同一个 gate，context_hash 不同，算新策略。

### 回退执行（run_agent 中的实现）

```python
if action == "switch" and node.skill_name in skill_chain.backtrack_map:
    backtrack_count += 1
    if backtrack_count > max_backtracks:  # max_backtracks = 5
        return f"Max backtracks exceeded at '{node.skill_name}'."
    target = skill_chain.backtrack_map[node.skill_name]
    node_idx = next(
        (i for i, n in enumerate(skill_chain.nodes) if n.skill_name == target),
        0,
    )
```

全局上限：最多 5 次回退。防止技能链在多个节点之间无限震荡。

---

## System Prompt 11 层组装

**文件**: `engine/prompt/assembler.py`

System Prompt 是 Agent 的"认知基础"。PromptAssembler 从 11 个层级逐层构建，每层负责一个维度的上下文。

| 层 | 来源文件 | 职责 | 缺失时行为 |
|---|---|---|---|
| 1 | `role.md` | 核心使命与身份定义 | 空字符串，跳过 |
| 2 | `style.md` | 行为风格与人格特质 | 空字符串，跳过 |
| 3 | `workflow.md` | 工作流 SOP，执行圣经 | 空字符串，跳过 |
| 4 | `toolbox.md` + ToolRegistry | 工具使用指南 + 动态可用工具列表 | 仅显示注册表 |
| 5 | SkillRegistry | 可用技能摘要列表 | 空字符串，跳过 |
| 6 | `expertise.json` | 核心能力声明（结构化） | 空字符串，跳过 |
| 7 | `traits.json` | 工作风格标签列表 | 空字符串，跳过 |
| 8 | `pipeline.json` | 交付承诺（task_type → pipeline 流程） | 空字符串，跳过 |
| 9 | `context.md` | 用户偏好（可被 UserPreferenceLearner 写入） | 空字符串，跳过 |
| 10 | `agents/output_style.md` | 输出格式规范（全局共享） | 空字符串，跳过 |
| 11 | `memory/` + 运行时上下文 | 记忆条目 + employee_id/name 等环境信息 | 空字符串，跳过 |

### 层间连接

所有非空层通过 `"\n\n---\n\n"` 分隔符拼接。空层自动过滤，不会产生连续分隔符。

### 第 4 层细节：工具列表动态注入

```python
tools_text = self._read(employee_dir / "toolbox.md")  # 静态指南
tool_list = tool_registry.list_tools()                  # 动态注册表
if tool_list:
    for t in tool_list:
        tools_text += f"- **{t.name}**: {t.description}"
```

确保 LLM 知道哪些工具真正可用，而不仅仅是模板里写了什么。

### 第 6-8 层细节：JSON 结构化层

每层通过 `_read_json_layer()` 加载 JSON 并用专用格式化函数转换：

- **expertise.json** → `_format_capabilities()`: `- **{name}**: {description}` 列表
- **traits.json** → `_format_work_styles()`: `标签: tag1, tag2, tag3` 单行
- **pipeline.json** → `_format_delivery()`: `- **{task_type}**: step1 → step2 → step3`

### 第 11 层细节：记忆加载

记忆加载有三个子部分：

1. **近期对话**：`memory/recent.jsonl` 最后 10 条，格式 `[timestamp] task → summary`
2. **作用域记忆**：先 `memory/project/` 再 `memory/agent/`，cap 20 条，每条截断 150 字符
3. **运行时上下文**：`context` dict 的 key-value 对

```python
# 加载优先级: project > agent > 根目录兼容
scoped_dirs = [
    (memory_dir / "project", "## Project Memories"),
    (memory_dir / "agent", "## Agent Memories"),
]
```

### 占位符渲染

**文件**: `engine/prompt/placeholder.py`

```python
def render_placeholders(text: str, variables: dict) -> str:
    # 替换 {{key}} 为 variables[key]，未知占位符保留原样
```

用于模板中的动态值注入，如 `{{employee_name}}`、`{{to_be_learned}}` 等。

---

## 记忆系统

**目录**: `engine/memory/`

### FileMemoryStore

**文件**: `engine/memory/store.py`

文件系统实现的记忆存储，双作用域设计：

```
memory/
├── agent/      # Agent 级记忆（个人经验）
├── project/    # 项目级记忆（跨 Agent 共享）
├── recent.jsonl  # 最近对话摘要
└── *.md        # 兼容旧版根目录文件
```

#### 存储格式

每条记忆是一个 `.md` 文件，YAML frontmatter + body + evidence：

```markdown
---
id: a1b2c3d4e5f6
scope: agent
created_at: 2024-01-15T10:30:00+00:00
last_accessed: 2024-01-15T10:30:00+00:00
---
Task: 修复登录页表单验证
Result: 发现是正则表达式缺少边界匹配...

Evidence: conversation at 2024-01-15T10:30:00+00:00
```

#### 搜索

基于关键词的简单匹配（不是向量搜索）：

```python
async def search(self, query: str) -> list[MemoryEntry]:
    keywords = query.lower().split()
    # 遍历所有 .md 文件，任意关键词命中即返回
```

Project 作用域的记忆排在搜索结果前面。

#### 对话记忆保存

`save_conversation_memory()` 在每次涉及工具调用的对话后执行：

1. 追加 `recent.jsonl`（task 前 100 字 + summary 前 200 字）
2. 写入 FileMemoryStore（agent 作用域）
3. 检查 dream 计数器，每 5 次对话触发 Dream 整理

### Dream 机制

**文件**: `engine/memory/dream.py`

灵感来源于人类睡眠时的记忆整理。每 5 次对话自动触发，4 个步骤：

#### 步骤 1: 过滤秘密

匹配 8 种秘密模式，命中即删除：

| 模式 | 匹配内容 |
|---|---|
| `sk-[A-Za-z0-9]{20,}` | OpenAI 风格 API key |
| `api[_-]?key\s*[:=]\s*\S+` | 通用 API key 赋值 |
| `password\s*[:=]\s*\S+` | 密码赋值 |
| `secret\s*[:=]\s*\S+` | Secret 赋值 |
| `token\s*[:=]\s*[A-Za-z0-9_\-\.]{16,}` | 长 token |
| `bearer\s+[A-Za-z0-9_\-\.]{16,}` | Bearer token |
| `ghp_[A-Za-z0-9]{36}` | GitHub Personal Access Token |
| `-----BEGIN (RSA )?PRIVATE KEY-----` | PEM 私钥 |

#### 步骤 2: 剪枝

删除 `last_accessed` 超过 30 天且未被重新访问的条目。

#### 步骤 3: 去重

基于关键词重叠度（Jaccard 变体，以较小集合为分母）：

```python
def _keyword_overlap(a: set[str], b: set[str]) -> float:
    intersection = a & b
    smaller = min(len(a), len(b))
    return len(intersection) / smaller
```

阈值 >= 0.70 视为重复。保留最新条目，将旧条目中的独有行合并进去。

#### 步骤 4: 模式提取

3+ 条目的关键词重叠度 >= 0.50 时，提取共同关键词作为主题摘要：

```
Pattern (5 entries): config, deployment, docker, nginx, server
```

创建为新的 agent 作用域记忆条目。

#### DreamReport

```python
@dataclass
class DreamReport:
    secrets_removed: int = 0
    merged: int = 0
    pruned: int = 0
    patterns_found: int = 0
    errors: list[str] = field(default_factory=list)
```

### UserPreferenceLearner

**文件**: `engine/memory/user_learner.py`

从对话中自动学习用户偏好，纯启发式（不调 LLM）。

#### 4 维探测

| 维度 | 函数 | 检测方式 | 可能值 |
|---|---|---|---|
| 语言 | `_detect_language()` | 字符频率分析 | `zh` (中文字符>10%) / `ja` (日文假名>5) / `en` (ASCII>80%) |
| 简洁度 | `_detect_verbosity()` | 词数统计 | `concise` (<=10词) / `detailed` (>=80词) |
| 技术水平 | `_detect_tech_level()` | 31 个专业术语匹配 | `expert` (命中>=2) / None |
| 代码风格 | `_detect_code_style()` | 9 对正则-标签 | `type hints` / `functional style` / `OOP` / `dataclasses` / `pydantic` / `async-first` |

专业术语列表（31个）：`async`, `await`, `decorator`, `metaclass`, `coroutine`, `mutex`, `semaphore`, `deadlock`, `race condition`, `O(n)`, `O(log n)`, `amortized`, `SOLID`, `DRY`, `YAGNI`, `DDD`, `kubernetes`, `k8s`, `docker`, `terraform`, `microservice`, `gRPC`, `protobuf`, `CI/CD`, `pipeline`, `rollback`, `sharding`, `replication`, `WAL`, `type hint`, `generic`, `protocol`, `反射`, `协程`, `线程池`, `事务`

#### 置信度机制

```python
_CONFIDENCE_THRESHOLD = 3  # 同一值观察到 3 次才写入
```

状态持久化在 `.learner_state.json`：

```json
{
  "counters": {
    "language": { "zh": 3, "en": 1 },
    "tech_level": { "expert": 2 }
  },
  "written": {
    "language": "zh"
  }
}
```

#### 写入策略

写入 `context.md` 时遵循严格规则：

1. 优先替换 `{{to_be_learned}}` 占位符
2. 如果字段已有真实值（非占位符），不覆盖用户手动设置的内容
3. 如果找不到字段，追加到 `# Preferences` / `# 偏好` 区域
4. 如果连 Preferences 区域都没有，放弃写入

---

## 完整执行流程示例

用户发送：**"帮我修复登录页的表单验证bug"**

### Step 1: 入口 — reply()

`reply(employee_id="emp-001", name="小张", user_message="帮我修复登录页的表单验证bug")`

加载 LLM 配置（四层覆盖合并）、初始化工具注册表和技能注册表。

### Step 2: Prompt 组装

`PromptAssembler.assemble()` 构建 11 层 System Prompt，包含角色定义、工具列表、记忆上下文等。

### Step 3: 任务路由

```python
route_task("帮我修复登录页的表单验证bug")
# "修复" 命中 _BUGFIX_KEYWORDS → bug_score=1
# 无 Feature 关键词命中 → feat_score=0
# → TaskType.BUGFIX
```

### Step 4: 构建技能链

```python
chain = SkillChain.bugfix_chain()
# sde-debug(RootCauseGate) → planning(PlanningGate) → testing-strategy(TestGate)
#   → change-validation(ValidationGate) → code-review(ReviewGate)
```

### Step 5: 节点 1 — sde-debug（根因分析）

LLM 进入 ReAct 循环，调用文件读取、搜索等工具定位 bug。

输出示例：
> 根因: 表单验证正则 `^[a-z]+$` 缺少大写字母匹配，导致包含大写字母的输入被拒绝。
> 证据: `login_form.py:42` 行的正则表达式，日志显示用户 "Admin" 输入被 reject。

→ SkillRubricGate: 长度>50, 有文件引用, 无错误标记 → **pass**
→ RootCauseGate: 有"根因", 有"证据"+"日志" → **pass**

### Step 6: 节点 2 — planning（修复规划）

LLM 制定修复计划。

输出示例：
> 1. 修改 `login_form.py:42` 的正则为 `^[a-zA-Z]+$`
> 2. 更新对应的单元测试，增加大写字母测试用例
> 3. 运行全量测试 → 验证: 确认所有测试通过

→ PlanningGate: 3 个编号步骤 + 含"验证" → **pass**

### Step 7: 节点 3 — testing-strategy（测试策略）

LLM 设计测试方案。

→ TestGate: >= 2 测试用例 + 含边界覆盖 → **pass**

### Step 8: 节点 4 — change-validation（变更验证）

LLM 执行代码修改并运行测试。

→ ValidationGate: 有执行证据 + pass/fail 计数 → **pass**

### Step 9: 节点 5 — code-review（代码评审）

LLM 对自己的修改做代码审查。

→ ReviewGate: P0/P1 分级 + 具体发现或 "no issues" → **pass**

### Step 10: 善后

1. `save_conversation_memory()` — 保存本次对话到记忆（因为用了工具，`had_tools=True`）
2. `UserPreferenceLearner.observe()` — 分析用户消息中的语言/技术水平等
3. `llm.close()` — 关闭 HTTP 连接
4. 返回最终结果给 server 层

---

## 文件映射总览

```
engine/
├── execution/                    # 执行控制层
│   ├── task_router.py           # 第1层: 任务分类 (TaskType 枚举 + 关键词匹配)
│   ├── skill_chain.py           # 第2层: 技能链 DAG (SkillNode + SkillChain + 回退映射)
│   ├── agent_loop.py            # 第3层: ReAct 循环 + 编排器 (run_agent/reply/reply_stream)
│   ├── gate.py                  # 门禁系统 (10个Gate实现 + GateResult)
│   └── backtrack.py             # 回退守卫 (FailureSignature + FailureLoopGuard)
│
├── safety/                       # 安全层
│   └── tool_guard.py            # 第4层: 工具调用安全拦截 (ToolGuard + GuardResult)
│
├── prompt/                       # Prompt 构建
│   ├── assembler.py             # 11层 System Prompt 组装 (PromptAssembler)
│   └── placeholder.py           # {{变量}} 占位符渲染
│
├── memory/                       # 记忆系统
│   ├── interface.py             # 抽象接口 (MemoryEntry + MemoryStore Protocol)
│   ├── store.py                 # 文件存储实现 (FileMemoryStore + save_conversation_memory)
│   ├── dream.py                 # Dream 整理 (DreamConsolidator + 4步骤)
│   └── user_learner.py          # 偏好学习 (UserPreferenceLearner + 4维探测)
│
├── llm/                          # LLM 客户端
│   ├── client.py                # OpenAI 兼容 HTTP 客户端 (LLMClient + ChatResponse)
│   └── model_config.py          # 配置解析 (ModelConfig + build_llm_client)
│
├── tool/                         # 工具系统
│   ├── interface.py             # 数据类型 (ToolDefinition + ToolCall + ToolResult)
│   ├── registry.py              # 工具注册表 (ToolRegistry + 自动发现 + 执行)
│   └── schema.py                # Python 函数 → JSON Schema 自动转换
│
├── skill/                        # 技能系统
│   ├── loader.py                # SKILL.md 解析 (YAML frontmatter + markdown body)
│   ├── registry.py              # 技能注册表 (SkillRegistry + builtin/employee 分离)
│   ├── executor.py              # 技能执行器 (注入 SKILL.md 为 system prompt + ReAct)
│   └── store.py                 # 版本控制 (SkillStore + .versions/ + diff + rollback)
│
├── plugin/                       # 插件系统
│   ├── registry.py              # 插件发现 (PluginManifest + PluginRegistry)
│   ├── loader.py                # handler.py 动态加载
│   └── trigger.py               # 触发器 (PollingTrigger + WebhookTrigger)
│
└── pyproject.toml                # 依赖: httpx, pyyaml, aiosqlite
```

关联文件（engine 外部）：

```
agents/
├── safety/
│   └── dangerous_commands.json  # 安全规则定义 (7大类24条)
├── tools/                        # 工具 provider Python 文件
├── skills/                       # 内置技能 SKILL.md 文件
└── output_style.md              # 全局输出格式规范 (Prompt 第10层)
```
