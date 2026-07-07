# 10 · 自研 Agent 框架深度解析

> 面试准备 + 技术内参。覆盖每个设计决策的 WHY，与主流框架的对比，以及 20+ 面试高频问题。

---

## 一、框架总览与设计哲学

### 1.1 为什么自研？

| 框架 | 核心问题 |
|---|---|
| **LangChain** | 过度抽象——5-6 层 wrapper，调试极难。Agent 纯 ReAct，没有代码级质量保障 |
| **CrewAI** | 流程控制全靠 LLM prompt——说"先规划再编码"，它可能跳过规划 |
| **AutoGen** | Agent 间对话式协作，但没有质量门禁——Agent A 说什么 B 直接信 |
| **AgentScope** | 纯 ReAct，LLM 决定一切，没有确定性编排层 |
| **Dify/Coze** | 可视化 DAG，无法做条件回退和失败循环检测 |

核心问题：**LLM 不可靠但有创造力，代码可靠但没创造力。怎么结合？**

### 1.2 核心设计原则：宏观确定性，微观 LLM 自由度

```
代码控制（确定性）：            LLM 控制（自由度）：
  ✅ 任务路由 → 规则引擎          🧠 理解需求 → ReAct 内
  ✅ 技能链顺序 → DAG              🧠 选工具选参数 → ReAct 内
  ✅ 质量检查 → 门禁               🧠 组织回复 → ReAct 内
  ✅ 失败回退 → backtrack_map
  ✅ 安全拦截 → 正则规则
```

不是"用 LLM 做 Agent"，而是**"用代码搭骨架，让 LLM 在骨架内自由发挥"**。

### 1.3 与主流的根本区别

```
纯 ReAct（LangChain）: LLM 决定一切 → 不可控
纯 DAG（Dify）:        代码决定一切 → LLM 只填槽
Agent-Smith:           DAG 控制宏观 → 每节点内 ReAct → 节点间门禁 → 失败可回退
```

---

## 二、四层嵌套执行模型

用户发一条消息，经历四层处理：

```
用户消息
  ├── 第 1 层：任务路由 ──── 代码控制（规则引擎）
  ├── 第 2 层：技能链 DAG ── 代码控制（有向图）
  ├── 第 3 层：ReAct 循环 ── LLM 控制（思考-行动-观察）
  └── 第 4 层：安全护栏 ──── 代码控制（正则拦截）
```

### 2.1 第一层：任务路由（engine/execution/task_router.py ~60行）

19 个 bugfix + 18 个 feature 关键词（中英文）计分，取高者。平局走 DIRECT。

**为什么规则不用 LLM？**
1. **速度**：<1ms vs 2-30s。路由在每条消息入口，不能慢
2. **确定性**：同一消息永远路由到同一结果。LLM 有 temperature 随机性
3. **可审计**：出问题直接看关键词命中。LLM 决策是黑箱

关键词失效时才 LLM fallback（route_task_with_llm）。用户可 `[bugfix]` 前缀覆盖。

**面试 Q: false positive？** → 计分制非布尔，"add a fix" 平局走 DIRECT。三层兜底（关键词→LLM→用户覆盖）。

**面试 Q: 为什么不直接 LLM 路由？** → 入口要快、稳、可审计。关键词 <1ms。只在失效时 fallback LLM——成本和可靠性的最优平衡。

### 2.2 第二层：技能链 DAG（engine/execution/skill_chain.py ~130行）

```python
@dataclass
class SkillNode:
    skill_name: str                          # 技能名
    gate: Gate                               # 门禁
    condition: Callable[[dict], bool] | None  # 条件跳过

class SkillChain:
    nodes: list[SkillNode]
    backtrack_map: dict[str, str]  # 失败回退到哪个上游节点
```

三条链：
```
Feature: planning → architecture(条件≥3文件) → testing-strategy → change-validation → code-review
Bug Fix: sde-debug → planning → testing-strategy → change-validation → code-review
Refactor: planning → testing-strategy → change-validation → code-review
```

**Bug Fix 多 sde-debug**：修 bug 必须先确认根因。"它能用了" ≠ "它修好了"。

**architecture 条件跳过**：改一个 CSS 颜色不需要架构评审。条件是"变更涉及 ≥3 文件"（正则提取 planning 输出的文件引用数量）。

**回退映射**：不是重试当前节点，而是回到上游重新来过——带失败原因。

**from_workflow_md()**：从 workflow.md 动态加载技能链——不同角色可有不同链，不用改 Python 代码。

**面试 Q: 和 LangGraph 区别？** → LangGraph 是通用图（环/分支/并行），我的是受限线性 DAG。刻意受限 = 可预测 = 易调试。Agent 工作流本质线性，不需要通用图复杂性。

### 2.3 第三层：ReAct 循环（engine/execution/agent_loop.py ~650行）

学术来源：Yao et al., 2022。LLM 交替"思考"和"行动"，行动结果作为下一次思考输入。

```python
async def _react_loop(llm, messages, tool_registry, tool_guard, max_iters=20):
    for _ in range(max_iters):
        if len(conversation) > 40:  # 滑动窗口
            conversation = [conversation[0]] + conversation[-30:]

        response = await llm.chat(conversation, tools=tools)
        if not response.has_tool_calls:
            return response.text  # 自然结束

        for tc in response.tool_calls:
            # 安全检查 → 执行 → 结果放回对话
            if tool_guard and not tool_guard.check(call).allowed:
                consecutive_errors += 1  # 连续失败检测
                continue
            result = await tool_registry.execute(call)
            # 3 次连续失败 → 注入换策略提示
```

**滑动窗口（40→30）**：20 次迭代可能 60+ 消息，超出上下文窗口。保留首条（system prompt）+ 最后 30 条。

**连续失败检测**：LLM 可能反复用同样参数调同一工具。3 次后注入 system 消息提示换方法——比直接停止更优雅。

**run_agent**：DIRECT 直接 ReAct；BUGFIX/FEATURE 走技能链（每节点执行技能 → SkillRubricGate → 节点Gate → 通过继续 / 失败查 FailureLoopGuard）。

**run_agent_stream**：全程 yield ExecutionEvent（SKILL_START/GATE_RESULT/BACKTRACK/TEXT_DELTA/DONE），前端实时渲染。

**面试 Q: ReAct vs Function Calling？** → Function Calling 是 API 协议（LLM 返回结构化工具调用），ReAct 是执行模式（循环交替 LLM+工具）。前者是后者的底层实现。

**面试 Q: 怎么判断停止？** → (1) 无 tool_calls = 自然结束；(2) max_iters=20 = 强制停止；(3) 连续失败 = 提示换方法。不依赖 LLM 自判。

**面试 Q: max_iters=20 够不够？** → 经验值。简单 3-5 次，复杂 10-15 次。>20 次通常卡住了，继续也没好结果。

### 2.4 第四层：安全护栏（engine/safety/tool_guard.py）

ToolGuard：28 条正则规则，8 大类（command_injection / resource_abuse / code_execution / network_abuse / sensitive_file_access / privilege_escalation / shell_evasion / destructive_command）。patterns + excludePatterns + 工具类型过滤。

FileGuard：工作目录白名单（~/、/tmp、cwd），敏感目录永久阻断（.ssh/.gnupg/.aws/.kube）。

**面试 Q: 正则防不住所有？** → 对。纵深防御：正则 → FileGuard → 输出截断 → 记忆过滤。长期加 LLM-based 安全层。

---

## 三、门禁系统（engine/execution/gate.py ~300行）

### 为什么需要？

LLM 输出形式正确但可能空洞。"1. 做 2. 做 3. 做 验证:查" 通过正则但没内容。

### 双层设计

SkillRubricGate（通用 pre-filter：长度>50 + 代码块/文件引用 + 无错误标记）→ 节点专属 Gate。

PlanningGate 和 ValidationGate 叠加了 LLMGate——正则通过后 LLM 语义验证。正则快但浅，LLM 慢但深。

10 个 Gate：PlanningGate(+LLM) / ValidationGate(+LLM) / TestGate / ReviewGate / RootCauseGate / DesignGate / SkillRubricGate / GitWorktreeGate / PRGate / TestDeliveryGate。

重试策略：3 次（调整参数 → 换策略 → blocked）。

**面试 Q: LLM 自己判自己？** → 评判比创作容易。判断"计划是否具体"比"一次生成完美计划"更可靠。可用不同模型做检查。

---

## 四、回退与失败循环守卫（engine/execution/backtrack.py ~40行）

FailureSignature = error_type + context_hash。record() → retry / switch / blocked。

不是限制重试次数，而是识别"同样方式犯同样错误"。max_same=2, max_strategies=2。

**面试 Q: 最坏情况？** → 4次/节点 × 5节点 × 20迭代 = 400次 LLM 调用。实际不会到。

---

## 五、System Prompt 11 层组装（engine/prompt/assembler.py ~230行）

| 层 | 来源 | 截断优先级 |
|---|---|---|
| 1 role.md | 身份 | 最高（不截断）|
| 2 style.md | 风格 | 高 |
| 3 workflow.md | SOP | 最高（不截断）|
| 4 toolbox.md + 注册表 | 工具 | 中 |
| 5 技能注册表 | 技能 | 中 |
| 6 expertise.json | 能力 | 低 |
| 7 traits.json | 标签 | 低 |
| 8 pipeline.json | 交付 | 最低 |
| 9 context.md | 偏好 | 中低 |
| 10 output_style.md | 格式 | 低 |
| 11 memory + runtime | 记忆+环境 | 中低 |

Token 预算 max_tokens=100k + 优先级截断。Prefix Cache（稳定层 MD5 hash 透传 LLM）。实测约 2500 tokens。

**面试 Q: 11 层太长？** → 实测 2500 tokens。预算管理是预防——记忆多时自动截断低优先级层。

---

## 六、记忆系统（engine/memory/ 6文件 ~1060行）

- **双作用域**：agent（跨项目）/ project（项目特定，优先级高）
- **Dream**：每 5 次对话（秘密过滤8种 → 30天剪枝 → 70%关键词去重 → 3+条模式提取）
- **四层 LLM 编译**：today/week/longterm/facts + MD5 指纹缓存
- **混合检索**：FTS5 + sqlite-vec(Jina v3, 1024维) + RRF(k=60) 融合
- **偏好学习**：4维检测(语言/简洁度/技术水平/代码风格) + 3次确认阈值 + context.md 占位符替换

**面试 Q: 和 MemGPT 区别？** → MemGPT 虚拟内存分页（LLM 决定换页），我们结构化（文件+编译+检索）。更可控。

**面试 Q: 为什么不直接 RAG？** → 也有 RAG（FTS5+vec），额外有编译——零散对话蒸馏成摘要。facts.md 几百字 vs RAG 几千字原始片段。

**面试 Q: Dream 名字来源？** → 人类睡眠记忆巩固。去噪、合并、提炼。

---

## 七、工具系统（engine/tool/ 4文件 ~270行）

TOOL_META 字典 + async execute() = 一个工具。无需类继承。自动发现（扫描 .py）+ MCP 集成（STDIO JSON-RPC）。

**面试 Q: 和 LangChain Tool 区别？** → 不需要继承类。一函数+一字典=一工具。

---

## 八、技能系统（engine/skill/ 4文件 ~210行）

| | 工具 (Tool) | 技能 (Skill) |
|---|---|---|
| 粒度 | 原子操作（一次调用） | 完整工作流（多次 LLM 迭代）|
| 执行 | 返回结果 | 注入 prompt + ReAct 循环 |
| 调用方 | LLM function calling | DAG 按顺序 |

SKILL.md = YAML frontmatter + Markdown。内置只读，Agent 可进化（SkillStore 10版本 + rollback + diff）。

**面试 Q: 为什么分开？** → 粒度不同。"code-review" 做工具只能一次生成报告，做技能可以逐步分析。

---

## 九至十二、其他子系统

- **插件**：Polling/Webhook/Cron 三种触发，动态加载 handler.py
- **会话恢复**：SessionCheckpoint 每节点保存，崩溃后恢复，session_id 防路径穿越
- **流式事件**：10 种 ExecutionEvent，run_agent_stream 全程 yield，SSE 到前端
- **LLM 配置**：环境变量→平台→模板→Agent→会话 五层覆盖，merge_configs 深合并

---

## 十三、与主流框架完整对比

| 维度 | Agent-Smith | LangChain | CrewAI | AutoGen | Dify |
|---|---|---|---|---|---|
| **架构** | DAG+ReAct 混合 | 纯 ReAct | 多Agent对话 | Agent消息 | 可视化DAG |
| **执行控制** | 代码宏观+LLM微观 | LLM控制 | LLM控制 | LLM控制 | 代码控制 |
| **质量保证** | 10 Gate+LLM验证 | 无 | 无 | Agent互评 | 无 |
| **失败处理** | LoopGuard+回退 | 无 | 无 | 重发消息 | 固定重试 |
| **记忆** | 双作用域+4层编译+混合检索 | BufferMemory | 共享 | 对话历史 | 变量传递 |
| **安全** | 28规则+FileGuard+记忆过滤 | 无 | 无 | 无 | 沙盒 |
| **学习** | 偏好自学+技能自进化 | 无 | 无 | 无 | 无 |
| **可观测** | 事件流+会话恢复 | LangSmith(付费) | 日志 | 日志 | 日志 |

---

## 十四、设计取舍与已知局限

| 选择 | 理由 | 局限 |
|---|---|---|
| 正则+LLM Gate | 快速过滤+深度检查 | LLM 自己判自己 |
| 文件+SQLite 存储 | 简单、可 git 版本化 | 大量记忆时扫描慢 |
| 串行技能链 | 节点间有依赖 | 无法并行 |
| 关键词优先路由 | 快、确定、可审计 | 覆盖有限 |

---

## 十五、面试高频 20 问

1. **为什么不用 LangChain？** → 过度抽象+纯 ReAct 不可控。需要代码级质量保障。
2. **和 Assistants API 区别？** → 在 function calling 上加了技能链/门禁/回退/记忆/安全。
3. **怎么防死循环？** → max_iters=20 + 3失败换策略 + FailureLoopGuard + max_backtracks=5。
4. **怎么做质量控制？** → 双层门禁（SkillRubricGate + 节点 Gate），关键 Gate 有 LLM 验证。
5. **记忆怎么防泄露？** → 写入拒绝密钥 + Dream 8种正则 + 编译 prompt 约束只记画像。
6. **DAG+ReAct 灵感？** → QoderWake 逆向分析。"硬骨架+软肌肉"。
7. **流式怎么保持一致？** → async generator 全程 yield 事件 + context dict 累积 + 检查点。
8. **怎么加新工具？** → agents/tools/ 新建 .py + TOOL_META + execute。无需改代码。
9. **怎么加新角色？** → agents/templates/ 新建目录+9个文件。server 自动扫描。
10. **五层架构好处？** → 测试隔离。换 Flask 只改 server/；换 Web 只改 app/。
11. **config 为什么四层？** → 灵活性平衡。全局→角色→个性化→临时。只需配最高优先级。
12. **技能和工具为什么分？** → 粒度不同。工具=原子操作，技能=完整工作流+多次 LLM 迭代。
13. **MCP 是什么？** → Anthropic 标准化工具协议。STDIO JSON-RPC 桥接到 ToolRegistry。
14. **正则能被绕过？** → 能。纵深防御：正则→FileGuard→输出截断→记忆过滤。
15. **偏好学习置信度？** → 4维检测+独立计数器+同特征3次才写入+不覆盖手写。
16. **重新设计改什么？** → Gate 全 LLM 验证 + 并行节点 + 文件记忆迁移 SQLite。
17. **Dream 名字来源？** → 人类睡眠记忆巩固。去噪、合并、提炼。
18. **11层 Prompt 太长？** → 实测 2500 tokens。token 预算管理是预防。
19. **最坏多少次 LLM 调用？** → 4×5×20 = 400次。实际不会到。
20. **多少行代码？** → ~3300行 Python，零 Agent 框架依赖。httpx+aiosqlite+pyyaml+sqlite-vec。

---

## 附录：文件映射

```
engine/ (~3300 行，零外部 Agent 框架依赖)
├── execution/   (~990)  agent_loop(650) task_router(60) skill_chain(130) gate(300) backtrack(40) events(50) session_state(70)
├── llm/         (~140)  client(120) model_config(20)
├── prompt/      (~245)  assembler(230) placeholder(15)
├── tool/        (~270)  interface(20) registry(90) schema(40) mcp_client(120)
├── skill/       (~210)  loader(40) registry(60) executor(30) store(80)
├── memory/      (~1060) interface(20) store(250) dream(240) compile(170) search(150) user_learner(230)
├── plugin/      (~260)  registry(90) trigger(130) loader(40)
└── safety/      (~100)  tool_guard(100)
```
