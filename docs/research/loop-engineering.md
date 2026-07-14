# Loop Engineering 调研

> 调研日期：2026-07-14。本文是对 [`cobusgreyling/loop-engineering`](https://github.com/cobusgreyling/loop-engineering) 的外部参考研究，不是 Agent-Smith 的实现规格。

## 结论

Loop Engineering 不是一个新的 Agent runtime，也不试图替代模型、工具调用或 ReAct loop；它是让 AI 编码 Agent **长期、重复、可控地运行**的外层控制面。仓库把调度、项目技能、显式状态、隔离 worktree、实现者/验证者分离、MCP、人工闸门和预算组合成可复制的“业务闭环”。这一定位可由其 Markdown 模式库、starters、GitHub Actions 和独立 Node CLI 工具的结构看出。[仓库根目录](https://github.com/cobusgreyling/loop-engineering) [README](https://github.com/cobusgreyling/loop-engineering/blob/main/README.md)

对 Agent-Smith 最值得借鉴的不是直接引入这套 TypeScript 工具，而是：将现在的单次任务运行时之上，补齐**可审计的 Run ledger、确定性止损、独立验证和按风险分级的自动化权限**。

## 它解决什么问题

项目将杠杆点从“写好一条 prompt”转向“设计能持续 prompt 和约束 Agent 的系统”。它定义六个原语：调度、worktree、skills、MCP/连接器、maker/checker 子 Agent，以及会话外的 memory/state；并给出 Daily Triage、PR Babysitter、CI/依赖扫描、变更日志等七种可复制模式。[README：原语和流程](https://github.com/cobusgreyling/loop-engineering/blob/main/README.md#the-five-building-blocks--memory) [模式注册表](https://github.com/cobusgreyling/loop-engineering/blob/main/patterns/registry.yaml)

其推荐的运行闭环是：

```text
调度/事件 → triage → 读写 STATE → 隔离 worktree → 实现者 → 验证者
          → MCP/Git/Ticket → 自动执行（仅低风险）或升级给人 → 下一轮
```

这个流程及人工闸门在项目 README 中有明确 Mermaid 定义；参考仓库本身也用 `LOOP.md` 说明哪些 loop 是 L1 报告、哪些仍需人工触发和验证。[README：Anatomy of a Loop](https://github.com/cobusgreyling/loop-engineering/blob/main/README.md#anatomy-of-a-loop) [LOOP.md](https://github.com/cobusgreyling/loop-engineering/blob/main/LOOP.md)

## 架构与关键实现

| 层 | 实现 | 工程意义 |
| --- | --- | --- |
| 声明层 | `patterns/registry.yaml`、各 pattern Markdown、`LOOP.md`、`STATE.md`、`loop-budget.md` 与 run log | 把任务目标、节奏、风险、状态和成本从聊天记录中移出，变为可审阅的项目工件。 [模式注册表](https://github.com/cobusgreyling/loop-engineering/blob/main/patterns/registry.yaml) [运行说明](https://github.com/cobusgreyling/loop-engineering/blob/main/LOOP.md) |
| 初始化与审计 | `loop-init` 生成 starter；`loop-audit` 从状态、skills、verifier、安全文档、worktree、预算、活动证据等信号计算 L0–L3，并且 L3 还要求真实活动和成本工件 | 将“能否无人值守”变为可重复检查的准入条件，而非主观判断。 [loop-audit 实现](https://github.com/cobusgreyling/loop-engineering/blob/main/tools/loop-audit/src/auditor.ts) [审计工作流](https://github.com/cobusgreyling/loop-engineering/blob/main/.github/workflows/audit.yml) |
| 运行上下文 | `loop-context` 保存本 run 的 goal/attempt ledger；确定性归一化错误、裁剪栈、合并重复失败；在重复错误、无进展、迭代数或 token 上限触发时升级人工 | 把“不要重复试”和成本止损做成无需 LLM 的、可测试的规则。 [context manager](https://github.com/cobusgreyling/loop-engineering/blob/main/tools/loop-context/src/context-manager.ts) |
| 配置漂移 | `loop-sync` 检查 `STATE.md`、`LOOP.md`、`AGENTS.md` 是否存在，且校验状态/配置引用及 skills 版本 | 认识到文档、状态与运行配置会逐步分叉，并提供轻量诊断。 [loop-sync 实现](https://github.com/cobusgreyling/loop-engineering/blob/main/tools/loop-sync/src/sync.ts) |
| 并行隔离 | `loop-worktree` 为每次 fix 建 `loop/<run-id>` worktree，并维护 manifest/status；默认只清理被拒绝或升级的 worktree，不强制删除含改动的目录 | 不让多个尝试直接污染主工作区，且把清理设计为保守操作。 [worktree 实现](https://github.com/cobusgreyling/loop-engineering/blob/main/tools/loop-worktree/src/worktree.ts) |
| MCP 边界 | 本地 MCP server 只解析已知状态文件、模式、skills、预算和安全文档；对 pattern/state 参数拒绝 `..`、路径分隔符等逃逸片段 | 项目知识的暴露面可枚举；外部连接器权限仍在安全规则中要求最小化。 [MCP resolver](https://github.com/cobusgreyling/loop-engineering/blob/main/tools/mcp-server/src/resolver.ts) [安全规则](https://github.com/cobusgreyling/loop-engineering/blob/main/docs/safety.md) |

安全模型是“默认不自动合并”。它要求 denylist、最小 MCP 权限、认证/支付/生产基础设施/多文件修改等人工审查，并用 L1 报告 → L2 小范围辅助修复 → L3 无人值守的阶段化升级；验证者必须独立于实现者并运行实际测试。[安全规则](https://github.com/cobusgreyling/loop-engineering/blob/main/docs/safety.md) [设计检查表](https://github.com/cobusgreyling/loop-engineering/blob/main/docs/loop-design-checklist.md) [生产运行准则](https://github.com/cobusgreyling/loop-engineering/blob/main/docs/operating-loops.md)

## 成熟度与边界

- **有用且正在落地。** 仓库已有模式、starters、测试过的 CLI 源码、CI 审计以及 npm 发布流程；目前可见的仓库 release 为 v1.5.0（2026-06-30）。[发布页](https://github.com/cobusgreyling/loop-engineering/releases/tag/v1.5.0) [README：工具与入门](https://github.com/cobusgreyling/loop-engineering/blob/main/README.md#getting-started-5-minutes)
- **不是完整编排引擎。** 它以跨工具的文档、脚手架和 CLI 为中心；真正的模型选择、调度后端、任务队列、身份认证、工具执行和故障恢复仍依赖 Claude/Codex/Grok、GitHub Actions 或使用者项目。因而它更像 Agent-Smith 的治理/运维层参考，而不是可直接嵌入的 engine 模块。[README](https://github.com/cobusgreyling/loop-engineering/blob/main/README.md) [工具目录](https://github.com/cobusgreyling/loop-engineering/tree/main/tools)
- **评分是启发式，不是安全证明。** `loop-audit` 很多信号来自文件存在、命名或文本提示；它能防止遗漏基本工件，却不能证明 verifier 真独立、测试充分或模型决定正确。因此不能把 L3 分数当作自动化授权本身。[auditor 源码](https://github.com/cobusgreyling/loop-engineering/blob/main/tools/loop-audit/src/auditor.ts)
- **并发控制仍在演进。** 文档已经把 parallel collision 列为 S2 风险，建议 worktree 和锁/队列；而当前公开的 #274 仍在讨论 multi-loop path locks。这意味着 worktree 隔离并不能单独解决同一文件、同一 issue 或同一状态文件的竞争。[失败模式](https://github.com/cobusgreyling/loop-engineering/blob/main/docs/failure-modes.md) [Issue #274](https://github.com/cobusgreyling/loop-engineering/issues/274)
- **参考仓库自身也未宣称所有 loop 都无人值守。** `LOOP.md` 中 PR Babysitter、Dependency Sweeper、CI Sweeper 仍标注为手动或部分自动；这比“所有 Agent 都可自动修复”的叙述更可信，也说明应从窄场景开始。[LOOP.md：Automation status](https://github.com/cobusgreyling/loop-engineering/blob/main/LOOP.md#automation-status-2026-07-10)

## 对 Agent-Smith 的可迁移方案

| 优先级 | 建议 | 落点与验收 |
| --- | --- | --- |
| P0 | 增加每个运行实例的结构化 `RunLedger`，而不是把尝试过程混入长期用户记忆 | 在 `engine/execution` 为 run 记录 goal、每轮 action、工具/测试证据、错误签名、tokens、状态和升级原因；只向下一轮注入裁剪后的事实摘要。连续同错、连续失败、迭代/预算超限必须产生终态事件。此思路直接对应 `loop-context` 的确定性 breaker。 |
| P0 | 将验证升格为运行时关卡 | 对会写文件或发起外部副作用的任务，明确 `implement → isolated verify → human/allowlist action`；验收以测试命令、退出码、改动范围和 verifier 结论为准，不能只让同一轮模型自称完成。Agent-Smith 已有 `run_stream_with_runtime`、任务路由和 MCP 边界，适合在其运行编排边界加入该状态机。 |
| P1 | 用风险等级控制自动化，而非按“是否用了 Agent”一刀切 | 先给定 L1（观察、摘要、提出建议）与 L2（worktree 内提出补丁）的产品契约；只有有预算、恢复/暂停开关、验证记录、denylist、人工升级路径的特定低风险模式才考虑 L3。此处应把 audit 作为**发布前检查**，不是授权替代品。 |
| P1 | 多 Agent 并发前先引入声明式租约 | worktree 之外，对 `issue/PR/path/state-file` 获取带 TTL 的 lease；一个 run 退出或被取消后必须释放/标记。用结构化状态取代多个 agent 并写一份 Markdown，直接覆盖 Loop Engineering 尚在解决的 path-lock 空白。 |
| P1 | 对齐配置、skills 与真实运行态 | 增加只读 health/audit：已加载 profile、可用 tools/MCP、强制 skill、测试命令、预算和状态 schema 是否相互匹配。重要的是从 Agent-Smith 的实际 `~/.agent-smith/agent/` 运行目录读取，而不是仅检查仓库模板。 |
| P2 | 保持“记忆”和“执行状态”两条线 | `recent.jsonl`/durable memory 解决跨会话学习；`RunLedger` 解决当前任务的去重、重试、止损和可复现排障。两者可互相引用，但不应互相充当源数据，否则短期错误与长篇工具输出会污染长期提示。 |

建议的首个试点是 **L1 CI/Issue triage**：固定 cadence 或事件触发、只读工具、输出结构化报告和 `RunLedger`、无行动时早退；稳定一到两周后才允许它在独立 worktree 生成补丁。这样能先验证成本、误报率、升级质量和状态闭环，再扩展到自动修复。

## 不建议直接照搬

不要将 `STATE.md`、`LOOP.md` 或 readiness score 当作 Agent-Smith 的唯一事实源；它们适合人类可读的运维界面，但并发、重试与权限决策必须落在可验证的结构化数据和运行时策略上。也不要先接入“全天候修复”：项目自己的失败模式明确列出了无限重试、验证戏剧、状态腐化、Token Burn 与并行碰撞，均应在 L1/L2 阶段用测试和运行记录量化后再扩大权限。[失败模式目录](https://github.com/cobusgreyling/loop-engineering/blob/main/docs/failure-modes.md)
