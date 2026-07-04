# 06 · Agent文件与技能系统设计参考

> 来源：QoderWake 本地文件逆向分析（2026-07-03）
> 目的：为 Agent-Smith 的Agent身份定义、技能打包、安全护栏、Hooks 系统提供设计参考

## 1. Agent身份文件系统

每个 Worker 用 8 个文件定义完整人格：

```
.qoder/
  IDENTITY.md              # 核心使命、不可妥协原则、完成标准、反目标
  PERSONA.md               # 工作风格、决策启发式、好习惯、反模式
  BIBLE.md                 # 完整工作流 SOP（含验证门禁）
  TOOLS.md                 # 可用工具和最佳实践
  USER.md                  # 用户信息（交互中自动学习填充）
  MEMORY.md                # 记忆索引
  CORE_CAPABILITIES.md     # 核心能力（JSON 数组）
  WORK_STYLES.md           # 工作风格标签（JSON 数组）
  DELIVERY_COMMITMENTS.md  # 交付承诺（JSON 数组，按任务类型定义管线）
```

IDENTITY 定义"我是谁"，PERSONA 定义"我怎么工作"，BIBLE 定义"我按什么流程交付"。三者组合构成完整的Agent人格。BIBLE 最复杂（约 600 行），包含任务路由、强制技能链、公共步骤（Understand → Investigate → Implement → Verify → Deliver），每步有 Gate / Output format / Backtrack trigger。

## 2. 技能系统 — SKILL.md

YAML frontmatter（name / description / argument-hint）+ Markdown 正文（AI 执行指令）。内置 9 个技能：planning / code-review / testing-strategy / sde-debug / architecture / system-design / change-validation-planner / git-worktree-branch / qoderwake-assistant。

## 3. Plugin — plugin.json

每Agent一个 Plugin，引用技能路径和 MCP 服务器配置。

## 4. Hooks — hooks.json

5 个事件：PreToolUse（权限守卫）、PostToolUse（变更追踪）、SessionStart（上下文+记忆）、UserPromptSubmit（远程文件）、PostCompact（记忆压缩）。

## 5. 安全护栏 — dangerous_shell_commands.json

24 条规则，7 类（command_injection / resource_abuse / code_execution / network_abuse / sensitive_file_access / privilege_escalation / shell_evasion）。规则格式：id / tools / params / category / severity / patterns / excludePatterns / description / remediation。

## 6. 版本管理

每个 Worker 的 Memory 和 Skills 用独立 git 仓库版本化。

## 7. Agent-Smith 采纳建议

P0: Agent 8 文件结构 / SKILL.md 格式 / 安全护栏
P1: plugin.json / hooks.json / 两层记忆
P2: MCP 内置端点 / Git 版本化 / 输出风格配置
