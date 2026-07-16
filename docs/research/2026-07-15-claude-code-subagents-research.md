# Claude Code Subagents 调研与 Agent-Smith 可迁移方案

> 范围：仅使用 Anthropic 的 Claude Code / Claude Agent SDK 官方文档。本文是调研结论与设计输入，**不是**当前实现规格，也不代表 Agent-Smith 已接入 Subagent。

## 结论先行

Claude Code 的 Subagent 是可复用的「受限子运行」机制：主 Agent 通过 `Agent` 工具交付一条任务说明，子 Agent 在**新的独立上下文窗口**里完成聚焦任务，原始工具调用、搜索结果和中间推理不进入主上下文；主 Agent 获得子 Agent 的最终消息并自行整合。[Claude Code Subagents](https://code.claude.com/docs/en/sub-agents)；[Agent SDK Subagents](https://code.claude.com/docs/en/agent-sdk/subagents)

这很适合 Agent-Smith 的探索、代码搜索、日志/测试归纳等高输出但可独立完成的工作。应迁移的是「独立上下文 + 明确任务契约 + 最小权限 + 可追踪生命周期 + 有限并发」；不应把它误解为多 Agent 共享自治，或把“上下文隔离”误当成“文件、工具和安全隔离”。

当前 Agent-Smith 的真实运行入口是 `run_stream_with_runtime()` → `_run_events_with_runtime()`：它为一次 run 准备运行时，调用 `run_agent_stream()`，持久化事件并清理 `RuntimeServices`。`RuntimeServices` 已拥有 LLM、`ToolRegistry`、`ToolGuard`、`background_llm` 和 MCP 客户端，`RunStateStore` 也已有 run 级持久化；但代码图中不存在 `Subagent` 符号或对应的子 run / 父子关系模型。因此这是新增编排能力，不能声称“已有子智能体”。

## Claude Code 的真实机制

| 维度 | 官方事实 | 对 Agent-Smith 的含义 |
| --- | --- | --- |
| 上下文与回传 | 非 fork 子 Agent 从空白上下文开始；拿到自己的 system prompt、委派任务、项目规则/记忆、工具定义等，但拿不到父会话、父工具结果或父 system prompt。父侧得到子 Agent 的**最终消息原文**作为工具结果。fork 是例外，会继承父会话。 | 子任务输入必须显式携带路径、错误、已作决定与输出格式。所谓“只回精简摘要”不是平台天然保证，必须由定义和调度器强制摘要 schema、字数/令牌上限。 |
| 委派 | Claude 依据任务与子 Agent `description` 自动匹配；也可显式指定。内置 Explore/Plan/general-purpose 分别覆盖只读探索、计划研究和可行动的复杂任务。 | v1 不应依赖纯自然语言自动匹配。先暴露显式 `delegate`，由主 Agent 或用户明确选择类型；之后再加受审计的路由策略。 |
| 前台/后台 | 前台阻塞父对话；后台并发。当前文档指出 v2.1.198 起后台为默认，必要时才前台等待；后台的权限请求会在主会话中显示。失败会以失败状态及可用的最后输出回报。 | 需要独立的 `queued/running/waiting_approval/completed/failed/cancelled/timed_out` 状态机、事件流和取消传播，不能把 `asyncio.create_task()` 当作完整后台能力。 |
| 工具与权限 | 默认继承父可用工具（含 MCP），可用 `tools` allowlist 与 `disallowedTools` denylist 收紧；子 Agent 的权限模式可配置，父级部分高权限模式会优先。可为某一子 Agent 单独挂 MCP，并在其结束时断连。 | 不能只复用父 `ToolRegistry` 的“全部工具”。调度前要按 **definition ∩ 父会话权限 ∩ ToolGuard** 构建子 registry；`ToolGuard` 仍是最后且不可绕过的执行边界。 |
| 模型与预算 | 可在定义或单次调用选择模型；未指定时继承主模型。Claude Code 的解析优先级是环境变量、单次调用、定义、主会话。官方把模型选择列为控制成本的手段；完成的 Agent 调用还可观测总 token、时长和工具调用数。 | Agent-Smith 应让 profile 定义模型/思考级别和每次/总 run token、时间、工具调用预算；预算耗尽必须是可见终态，不能只依赖厂商额度错误。 |
| 并发与嵌套 | 独立任务可并行；子 Agent 也可嵌套，深度固定上限为 5。官方文档没有给出可作为产品默认值的并发上限。 | v1 禁用嵌套，做每个父 run 和全局的可配置并发槽；不要照搬 5 层。并发槽、排队、公平性和取消需由 Agent-Smith 自己定义。 |
| 隔离 | 上下文隔离不等于工作目录隔离：默认在父的当前工作目录运行，只有 `isolation: worktree` 才给临时 Git worktree。 | 探索型 worker 默认只读；任何写入型 worker 必须显式选择隔离工作区、专属 run 目录或 approval，避免同一仓库并发写冲突。 |

### 需要精确理解的两个边界

1. **“摘要回传”需要产品契约。** SDK 文档说父收到的是子 Agent final message verbatim，而 Claude Code 再由父决定是否概括。故 Agent-Smith 需要在委派提示中规定结构化输出，例如 `findings`（最多 5 项）、`evidence`（路径/命令）、`recommendation`、`uncertainties`，再由 executor 对超限输出做截断/摘要；禁止把完整 transcript 回灌父 prompt。
2. **“独立上下文”不能放松安全。** Claude 的 Explore/Plan 为节省成本甚至跳过项目规则和 Git 状态；这不适合直接复制到 Agent-Smith，因为项目策略、租户身份、工作目录约束和 `ToolGuard` 是安全边界，必须由 runtime 传递并每次执行强制检查。

## 适合 Agent-Smith 的最小可行方案

先只解决“高噪声、可独立、只需结论”的任务，不把核心多步骤实现分裂成多个可写 worker。

### v1 的三个固定类型

| 类型 | 默认模型与权限 | 适用任务 | 回传 |
| --- | --- | --- |
| `explore` | 低成本模型；只读文件/搜索/代码图 | 定位调用链、模块盘点、风险初筛 | 证据化发现，最多 5 条 |
| `research` | 网络读工具 + 只读本地工具；无写入 | 官方资料、依赖或竞品调研 | 来源 URL、事实、置信度、不确定项 |
| `test_probe` | 指定测试命令；无编辑、无网络写 | 运行测试、复现并归纳失败 | 命令、通过/失败、关键错误、下一步 |

将 `implement`、通用 Bash、任意 MCP、文件写入和嵌套委派排除在 v1 之外。它们跨越的安全/并发/合并语义太多，先由主 Agent 在已有 approval 流中执行。

### 建议的内部契约

```text
Parent run
  └─ delegate(type, task, input_refs, output_contract, budget)
       └─ Child run (独立 history / 独立 LLM 调用 / 派生 tool registry)
            └─ terminal summary event
  └─ Parent receives summary reference, decides whether to cite/采用/继续
```

建议新增但尚未实现的实体：

- `SubagentDefinition`：name、description、system prompt、model policy、allowlist、max turns/token/time、允许后台与输出 schema；项目配置可声明，但内置类型优先。
- `SubagentTask`：`task_id`、`parent_run_id`、definition、输入引用（不是整个 history）、状态、预算、时间戳、取消原因、summary artifact 引用。
- `SubagentExecutor`：创建独立 LLM 会话与派生 `RuntimeServices`，将所有工具调用仍经 `ToolGuard`，运行后保存完整 transcript 作为审计 artifact。
- `SubagentScheduler`：每父 run 1–2 个并发槽、全局槽、FIFO 排队、deadline、超时与取消传播；v1 `max_depth=1`。
- 事件/SSE：`subagent_queued`、`subagent_started`、`subagent_progress`（仅轻量状态）、`subagent_summary`、`subagent_failed`、`subagent_cancelled`。Shell 默认展示状态和最终摘要，不把子工具输出混入主 transcript。

### 验收条件

1. 子任务读取 100 个文件或测试输出 1MB，父 prompt 增量仍仅为受限 summary；可从 artifact 追溯证据。
2. 子任务无法调用未列入 allowlist 的工具；任何实际工具调用均经过现有 `ToolGuard` 与 approval/run 关联。
3. 主 run 取消、用户拒绝 approval、子 run 超时、模型错误都留下确定终态，并不会让父 run 永久等待。
4. 两个只读子任务可并行，写入型任务在 v1 被拒绝；不会共享/竞争父 run 的 memory 写入或同一 `RuntimeServices` 关闭责任。
5. SSE 与 shell 能显示树状父子关系、运行时间、失败/超时原因和摘要；恢复只针对显式保存的子 run，不自动把旧结论当作当前事实。

## 不能照搬及风险

- **无需照搬 Claude 的自动调度。** `description` 匹配有不可预测性；Agent-Smith 应以显式工具 schema 与门槛（任务类型、预算、是否可后台）为先。
- **不要复制 Explore/Plan 的规则跳过。** Agent-Smith 的运行时身份、目录范围、工具策略和审批不是可选提示，必须入子 run。
- **不要共享可关闭资源。** 当前 `RuntimeServices.close()` 会关闭 MCP 与 LLM 客户端；子 run 若共享同一实例，一个子任务结束即可误关父资源。子任务要么拥有自己的 clients，要么使用具有引用计数/由父统一关闭的共享池。
- **不要默认并行写目录。** 默认同一 cwd 的语义会产生竞态、污染父工作区与难以归因的工具结果；先只读，后续再以 worktree/overlay 加 approval 引入写入型 agent。
- **不要把子输出直接写入记忆。** 研究结论、失败日志和模型推断必须先标为来源明确的 artifact；只有被主 Agent 验证/用户采纳的结论才能进入现有 memory 学习流程。
- **成本与退化必须显式。** 多个子 LLM 调用会增加总 token、延迟和限流面；为每种定义配置预算，记录用量，失败时返回“未完成 + 部分证据”，而非把最后一段文本当成结论。

## 官方来源

- [Create custom subagents — Claude Code Docs](https://code.claude.com/docs/en/sub-agents)：内置 agent、定义/作用域、模型选择、工具/权限/MCP、前后台、嵌套、上下文载入与恢复。
- [Subagents in the SDK — Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/subagents)：独立上下文、父子回传、定义方式、事件识别与 transcript 生命周期。
- [Tools reference — Claude Code Docs](https://code.claude.com/docs/en/tools-reference)：`Agent`、`SendMessage`、`TaskStop` 的工具语义。
- [Manage multiple agents with agent view — Claude Code Docs](https://code.claude.com/docs/en/agent-view)：后台会话的状态与交互式监控语义（研究预览）。
- [Hooks reference — Agent response](https://code.claude.com/docs/en/hooks#agent)：Agent 调用完成时可观测的最终文本、token、时长和工具调用计数。
- [Monitoring usage](https://code.claude.com/docs/en/monitoring-usage) 与 [Models, usage, and limits](https://support.claude.com/en/articles/14552983-models-usage-and-limits-in-claude-code)：嵌套调用的可观测性和模型/用量的成本边界。
- [Official `code-review` plugin](https://github.com/anthropics/claude-code/tree/main/plugins/code-review)：官方插件中并行多项审查再收敛/过滤的可参考 fan-out 模式；不是核心运行时实现。

## 待进入正式设计时要先定的决策

1. 用户/主 Agent 如何显式触发：新 `delegate` tool、命令，还是自动路由？建议 v1 仅新 tool。
2. 哪些 provider/profile 支持 background LLM；无法并发时是排队、降级前台还是拒绝？
3. 子 run transcript/artifact 的保存位置、保留期、访问权限与脱敏策略。
4. summary schema 的强制方式和最大尺寸；是否允许主 Agent 请求一次补充而非重跑。
5. 第二阶段是否允许 write worker；若允许，worktree 生命周期、diff 回传、测试、approval 和合并责任由谁承担。
