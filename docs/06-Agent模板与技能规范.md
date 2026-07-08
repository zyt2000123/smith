# Agent 模板与技能规范

本文档描述 Agent-Smith 的角色模板文件格式、内置技能规范、工具 Provider 接口、安全规则和技能自进化机制。

---

## 1. 角色模板文件格式

每个角色模板是 `agents/templates/<role-name>/` 目录下的 9 个文件，完整定义一个 Agent 的身份、行为和能力边界。

### 1.1 config.yaml — 元信息

```yaml
name: 后端工程师
role: backend-engineer
description: 负责服务端 API 开发、数据模型设计和系统集成
llm:
  model: null  # null 表示继承上层配置（平台级 → 模板级 → Agent 级 → 会话级）
knowledge:
  - api-design
  - database-modeling
  - authentication
  - caching-strategies
  - message-queues
tools:
  enabled:
    - read_file
    - write_file
    - shell
    - search_knowledge
    - web_fetch
    - skill_load
    - memory_ops
```

关键字段说明：

| 字段 | 类型 | 含义 |
|------|------|------|
| `name` | string | 显示名称（中文） |
| `role` | string | 角色标识（kebab-case，同目录名） |
| `description` | string | 一句话职责描述 |
| `llm.model` | string \| null | LLM 模型名，null 继承上层 |
| `knowledge` | list[string] | 知识领域标签，用于知识库检索 |
| `tools.enabled` | list[string] | 允许使用的工具名单 |

### 1.2 role.md — "我是谁"

定义 Agent 的核心身份：

- **Core Mission** — 一句话使命宣言
- **Non-Negotiable Principles** — 不可协商的原则（通常 4-5 条）
- **Done Criteria** — 什么算"完成"的可验证标准
- **Anti-Goals** — 明确列出"不做什么"，划定职责边界

示例（后端工程师）：
```markdown
# Core Mission
设计和实现可靠、安全、高性能的服务端系统，为前端和外部系统提供稳定的 API 和数据服务。

# Non-Negotiable Principles
1. API 契约即文档：接口先定义后实现，变更必须向后兼容
2. 数据完整性第一：所有写操作必须有事务保护和幂等设计
3. 安全无例外：输入校验、权限检查、SQL 参数化，无一可省
...

# Anti-Goals
- 不做前端页面开发和 UI 调整
- 不做基础设施层面的运维（交给 DevOps）
```

### 1.3 style.md — "我怎么工作"

定义 Agent 的工作风格和决策方式：

- **Working Style** — 工作风格描述（自底向上/自顶向下等）
- **Decision Heuristics** — `When <场景>: <决策>` 格式的启发式规则
- **Good Habits** — 推荐的好习惯
- **Anti-Patterns** — 明确禁止的反模式

### 1.4 workflow.md — "我按什么流程交付"

完整的工作流 SOP，包含：

**任务路由**（3 条路由 + 直接回复）：

| 路由 | 触发条件 | 技能链 |
|------|---------|--------|
| Bug Fix | 异常日志、错误响应、数据不一致 | `sde-debug → planning → testing-strategy → change-validation → code-review` |
| Feature | 新功能、数据模型变更、服务集成 | `planning → architecture(仅大型变更) → testing-strategy → change-validation → code-review` |
| Refactor | 性能优化、架构调整、技术债清理 | `planning → testing-strategy → change-validation → code-review` |
| 简单问答 | 不涉及代码变更的咨询 | 直接回复 |

**强制技能链硬规则**：
- Bug Fix **必须**使用 sde-debug 和 testing-strategy，不可跳过
- architecture 仅在变更涉及 3+ 文件或跨模块时触发
- code-review **始终**是最后一步，不可跳过
- testing-strategy 必须在 change-validation 之前完成

**公共 5 步骤**（所有路由共享）：

1. **Understand（理解）** → 门禁：能准确复述需求 + 识别至少 3 个边界条件 + 明确数据流向
2. **Investigate（调查）** → 门禁：已确认可复用资源 + 技术方案可行 + 依赖已明确
3. **Implement（实现）** → 门禁：实现方案与规划一致 + 接口契约完整 + lint 零错误
4. **Verify（验证）** → 门禁：测试全部通过 + 无 N+1 查询 + 无回归 + 迁移可回滚
5. **Deliver（交付）** → 门禁：测试实际运行并通过 + API 文档已更新 + 迁移回滚已验证

**回退策略**：
```
Implementation 失败 → 回退到 Planning，重新评估方案
Verify 失败 → 回退到 Implementation，修复后重新验证
同一失败出现 2 次 → 换策略（不同技术方案/架构）
换策略后仍失败 → 上报用户，附带已尝试方案和失败原因
```

### 1.5 toolbox.md — "我能用什么工具"

工具清单，按用途分组，附最佳实践：
```markdown
## Code Editing
- **read_file** — 阅读现有服务代码、配置、迁移文件
- **write_file** — 创建新的模型、服务、路由、测试文件
- **shell** — 运行测试、数据库迁移、代码检查

## Investigation
- **search_knowledge** — 查询 API 文档、数据库 schema、架构决策记录
- **web_fetch** — 获取第三方服务文档和技术方案

## Workflow
- **skill_load** — 加载 planning / code-review / sde-debug / architecture 技能
- **memory_ops** — 记录架构决策、接口变更历史、已知问题
```

### 1.6 context.md — 用户偏好

包含 `{{to_be_learned}}` 占位符的用户画像模板，由 `UserPreferenceLearner`（`engine/memory/user_learner.py`）在交互过程中自动填充：

```markdown
# User Profile
- Name: {{to_be_learned}}
- Preferred Language: {{to_be_learned}}
- Communication Style: {{to_be_learned}}
- Technical Level: {{to_be_learned}}
- Code Style: {{to_be_learned}}

# Preferences
(Auto-filled through interaction)
```

### 1.7 expertise.json — 核心能力列表

```json
[
  {"name": "api-development", "description": "RESTful/GraphQL API 设计与实现，含版本管理和文档生成"},
  {"name": "database-design", "description": "关系型和文档型数据库建模、迁移管理、查询优化"},
  ...
]
```

### 1.8 traits.json — 工作风格标签

```json
["system-thinking", "data-first", "contract-driven", "defensive-coding", "observability-aware"]
```

### 1.9 pipeline.json — 交付管线

按任务类型定义有序执行步骤：

```json
[
  {"task_type": "feature", "pipeline": ["define-api-contract", "design-data-model", "write-migration", "implement-repository", "implement-service", "implement-controller", "write-tests", "update-api-docs", "pr-with-test-report"]},
  {"task_type": "bugfix", "pipeline": ["reproduce-with-logs", "trace-request-flow", "identify-root-cause", "fix-and-add-test", "verify-no-regression", "pr-with-evidence"]},
  {"task_type": "review", "pipeline": ["check-api-contract", "review-sql-queries", "verify-error-handling", "check-security", "validate-test-coverage"]},
  {"task_type": "migration", "pipeline": ["backup-strategy", "write-migration", "test-rollback", "migrate-staging", "verify-data-integrity", "migrate-production"]}
]
```

---

## 2. 内置角色模板

9 个内置模板，位于 `agents/templates/` 目录下：

| 模板目录 | 角色名称 | shell-native 默认 | 特化领域 |
|----------|---------|-------------------|---------|
| `personal-assistant` | 个人助手 | Yes | 目标澄清、本地执行、信息检索、写作整理、长期上下文维护 |
| `backend-engineer` | 后端工程师 | Yes | API 开发、数据库设计、安全、缓存策略、消息队列 |
| `frontend-engineer` | 前端工程师 | Yes | React 模式、CSS 布局、无障碍、性能优化、设计系统 |
| `devops-engineer` | 运维工程师 | Yes | CI/CD 管道、容器编排、IaC、监控告警、云服务 |
| `test-engineer` | 测试工程师 | Yes | 测试模式、测试框架、边界分析、Mock 策略、CI 测试 |
| `data-analyst` | 数据分析师 | Yes | SQL 分析、统计方法、数据可视化、业务指标、数据质量 |
| `product-manager` | 产品经理 | Yes, 可按配置收窄 | 用户研究、产品策略、需求撰写、数据分析、竞品分析 |
| `content-ops` | 内容运营 | Yes, 可按配置收窄 | 技术文档、内容策略、风格指南、信息架构、SEO 基础 |
| `ui-designer` | UI 设计师 | Yes, 可按配置收窄 | 设计系统、交互模式、视觉层级、无障碍标准、响应式设计 |

**shell-native 默认**：Agent-Smith 的 Agent 定位是本地终端原生执行体，默认具备 shell 能力；产品/内容/设计类模板也不再从产品定义上禁止 shell。是否收窄某个 Agent 的工具集，应通过 `employees/<id>/config.yaml` 的 `tools.enabled/disabled` 或更细粒度 guard 配置完成，而不是把「角色类型」和「本地执行权限」绑定死。

**共性**：所有模板共享同一工作流骨架（5 步：Understand → Investigate → Implement → Verify → Deliver）和强制技能链，差异仅在领域专有内容（知识标签、专家能力、风格标签、管线步骤）。

---

## 3. SKILL.md 格式规范

技能是 Markdown 文件，使用 YAML frontmatter 声明元信息：

```yaml
---
name: planning
description: "制定实现计划，输出步骤、验证点和风险项"
version: "1.0"
trigger: task_start
trigger_condition: "(可选) 触发条件描述"
input: "task description or requirement"
output: "numbered implementation plan with verification points"
---

# Planning

## Goal
[目标描述]

## Process
[步骤流程]

## Output Format
[输出格式模板]
```

### Frontmatter 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | Yes | 技能唯一名称，kebab-case |
| `description` | Yes | 一句话描述技能作用 |
| `version` | Yes | 语义化版本号 |
| `trigger` | No | 触发时机（`task_start`, `on_error`, `pre_implement`, `large_change`, `pre_review`, `pre_commit`） |
| `trigger_condition` | No | 触发条件的详细描述 |
| `input` | No | 技能期望的输入描述 |
| `output` | No | 技能产出的输出描述 |

### 正文结构

- **Goal** — 技能的目标
- **Process / Steps** — 执行步骤或流程
- **Output Format** — 输出的 Markdown 模板（通常用代码块给出）

---

## 4. 内置技能

6 个内置技能，位于 `agents/skills/` 目录下，只读不可修改：

| 技能 | 触发时机 | 核心作用 |
|------|---------|---------|
| `planning` | `task_start`（任务开始） | 需求澄清 → 范围界定 → 步骤分解（3-7 步） → 风险识别 → 计划确认 |
| `architecture` | `large_change`（3+ 文件跨 2+ 模块） | 一致性 / 可维护性 / 可扩展性 / 安全性 / 性能 五维评审，输出 ADR |
| `sde-debug` | `on_error`（遇到错误） | 复现 → 假设（2-3 个） → 验证 → 修复。铁律：不确认根因不修复 |
| `testing-strategy` | `pre_implement`（实现前） | 测试金字塔选择 + 关键用例 + 边界用例 + 显式"不测试"项 |
| `change-validation` | `pre_review`（Review 前） | 构建 / 测试 / 回归 / 约定 / 安全 五项检查，输出 PASS/FAIL 报告 |
| `code-review` | `pre_commit`（提交前） | 正确性 / 安全 / 性能 / 可读性 四维审查，四级严重性（critical/major/minor/nit） |

### 技能间的调用顺序

技能通过 `engine/execution/skill_chain.py` 按链式顺序执行。典型调用链：

```
Feature:  planning → [architecture] → testing-strategy → change-validation → code-review
Bug Fix:  sde-debug → planning → testing-strategy → change-validation → code-review
Refactor: planning → testing-strategy → change-validation → code-review
```

### sde-debug 铁律

```
不修复没有确认根因的问题。"能跑了"不等于"修好了"。
```

每个结论都需要对应的证据（日志片段、变量值、测试结果）。"我觉得"不是证据。

### code-review 严重性级别

| 级别 | 含义 | 示例 |
|------|------|------|
| `critical` | 必须修复才能合并 | Bug、安全漏洞、数据丢失风险 |
| `major` | 强烈建议修复 | 性能问题、错误处理缺失 |
| `minor` | 建议改进 | 命名、注释、代码风格 |
| `nit` | 可选优化 | 个人偏好级别的建议 |

---

## 5. 工具 Provider 接口

所有工具位于 `agents/tools/` 目录下，每个 `.py` 文件是一个独立工具 Provider。

### 接口约定

每个工具文件需要导出两样东西：

```python
# 1. TOOL_META — 工具元信息字典
TOOL_META = {
    "name": "tool_name",                    # 唯一标识
    "description": "工具的一句话描述",         # 展示给 LLM
    "parameters": {                          # JSON Schema
        "type": "object",
        "properties": { ... },
        "required": [...]
    }
}

# 2. async def execute(**kwargs) -> str — 异步执行函数
async def execute(*, param1: str, param2: int = 0) -> str:
    # 执行逻辑
    return "结果字符串"
```

### 自动发现机制

`engine/tool/registry.py` 中的 `ToolRegistry.load_providers()` 扫描 `agents/tools/` 目录下所有 `.py` 文件（跳过 `_` 开头的），自动注册发现的工具。无需手动注册。

### 9 个内置工具

| 工具 | 关键参数 | 行为特征 |
|------|---------|---------|
| `read_file` | `path`, `offset`, `limit` | 50KB 上限，返回带行号的文本，超限需用 offset/limit 分段读取 |
| `write_file` | `path`, `content`, `append` | 写入前校验是否在工作目录内，自动创建父目录，支持追加模式 |
| `shell` | `command`, `timeout`, `cwd` | 默认 30s 超时（最大 120s），输出截断 10KB，通过 `asyncio.create_subprocess_shell` 执行 |
| `search_knowledge` | `query`, `top_k`, `category` | 知识库搜索（当前为 Stub，待连接 Hub 向量/全文索引） |
| `web_fetch` | `url`, `timeout` | 仅允许 http/https，50KB 内容上限，默认 15s 超时（最大 30s），阻止 file/ftp/data scheme |
| `skill_load` | `name` | 按名称加载 `agents/skills/<name>/SKILL.md`，找不到时列出可用技能 |
| `skill_manage` | `action`, `employee_id`, `skill_name`, ... | 7 个操作：list/get/create/edit/patch/versions/rollback。内置技能只读 |
| `memory_ops` | `action`, `employee_id`, `query`/`content`/`evidence`/`memory_id` | 4 个操作：search/add/update/remove。强制要求 evidence，自动拒绝含敏感信息（API key、密码等）的记忆 |
| `git_ops` | `action`, `cwd`, `branch`, `message`, `files`, ... | 8 个操作：status/diff/branch_create/commit/push/worktree_create/worktree_remove/discover。提交前自动检查敏感文件（.env, .pem, .key, .ssh/ 等） |

### 工具输出截断

`ToolRegistry.execute()` 对所有工具输出强制 4000 字符上限，超出部分自动截断并附加 `[truncated]` 标记，以保护 LLM 上下文窗口。

---

## 6. 安全规则

安全规则定义在 `agents/safety/dangerous_commands.json`，由 `engine/safety/tool_guard.py` 在工具执行前检查。

### 7 大类 24 条规则

| 类别 | ID 范围 | 条数 | 典型拦截目标 |
|------|---------|------|-------------|
| `command_injection` | cmd-inj-001 ~ 004 | 4 | 管道到 shell 解释器、反引号/`$()` 命令替换、`eval`、变量注入 |
| `resource_abuse` | res-abuse-001 ~ 003 | 3 | Fork bomb、无退出条件的死循环、创建超大文件 |
| `code_execution` | code-exec-001 ~ 004 | 4 | Python eval/exec 内联、动态 import、`compile()` 滥用、`node -e` 内联执行 |
| `network_abuse` | net-abuse-001 ~ 003 | 3 | 向外部 POST 数据、反向 shell、端口扫描 |
| `sensitive_file_access` | sens-file-001 ~ 004 | 4 | /etc/passwd, .ssh/, .env, .pem/.key 私钥文件 |
| `privilege_escalation` | priv-esc-001 ~ 003 | 3 | sudo/su 提权、chmod 777、setuid/setgid |
| `shell_evasion` | sh-evade-001 ~ 003 | 3 | Base64 解码后管道到 shell、清除 history、覆盖标准命令别名 |

### 规则结构

每条规则包含：

```json
{
  "id": "cmd-inj-001",
  "tools": ["shell"],             // 适用的工具列表
  "category": "command_injection", // 分类
  "severity": "critical",         // critical 或 major
  "patterns": ["..."],            // 正则匹配模式
  "excludePatterns": ["..."],     // 排除模式（白名单）
  "description": "...",           // 风险描述
  "remediation": "..."            // 修复建议
}
```

**severity 说明**：
- `critical` — 直接阻止执行，不可绕过
- `major` — 警告并要求确认

---

## 7. 技能自进化

### 内置 vs Agent 技能

| 属性 | 内置技能 | Agent 技能 |
|------|---------|---------|
| 位置 | `agents/skills/<name>/SKILL.md` | `~/.agent-smith/employees/<id>/skills/<name>/SKILL.md` |
| 可修改 | No（只读） | Yes |
| 版本控制 | Git 跟踪 | SkillStore 版本快照 |
| 来源 | 系统预装 | Agent 创建或进化 |

### SkillStore 版本管理

`engine/skill/store.py` 中的 `SkillStore` 为每个 Agent 技能维护版本快照：

```
~/.agent-smith/employees/<id>/skills/<name>/
    SKILL.md            # 当前版本
    .versions/          # 历史快照
        20260704T120000.md
        20260704T130000.md
        ...
```

- 保留最近 **10 个版本**快照，超出自动清理最老的
- 每次 edit 或 patch 操作前自动保存当前版本
- rollback 前也会保存当前版本（不丢失回滚前的状态）
- 支持 `diff` 操作比较任意两个版本（含 `"current"` 特殊值）

### skill_manage 工具 7 个操作

| 操作 | 必填参数 | 说明 |
|------|---------|------|
| `list` | `employee_id` | 列出所有技能（内置 + Agent），含来源标记 |
| `get` | `employee_id`, `skill_name` | 读取技能内容（优先 Agent 版本，其次内置） |
| `create` | `employee_id`, `skill_name`, `content` | 创建新 Agent 技能（不可与内置技能同名） |
| `edit` | `employee_id`, `skill_name`, `content` | 全文替换 Agent 技能（自动存版本） |
| `patch` | `employee_id`, `skill_name`, `section`, `section_content` | 按 Markdown 章节局部替换（自动存版本） |
| `versions` | `employee_id`, `skill_name` | 列出版本快照清单 |
| `rollback` | `employee_id`, `skill_name`, `version_id` | 回滚到指定版本 |
