# 13 · 单常驻 Agent 架构重梳理

## 1. 为什么要重梳理

Agent-Smith 早期沿用了"数字员工"模型：可以创建多个 employee，每个 employee 从模板复制一份运行时目录，API 和数据库都围绕 `employees/<id>` 展开。

现在产品定位已经收口：**Smith 是用户电脑上的唯一常驻 Agent**。技能、工具、知识注入负责扩展能力，不再通过增加多个 Agent/员工来扩展产品形态。

因此，`employee` / `employees/<id>` 不应再作为目标架构概念，只能作为历史兼容壳存在。

## 2. 新的核心设计理念

1. **一个常驻主体**：用户面对的是 Smith，一个长期运行、持续积累上下文的本机 Agent。
2. **能力扩展不等于角色扩增**：新增能力走 `skills`、`tools`、`knowledge`，不是新建一个 Agent。
3. **运行时档案是单数**：Smith 的身份、偏好、技能、记忆、配置都归入一个本地档案目录。
4. **框架和内容分离**：`engine/` 是执行机制；`agents/` 是内容资产库；`~/.agent-smith/agent/` 是用户本机的可变运行时资产。
5. **兼容层可存在，但不能塑造心智**：旧的 `employees` 表、路由、目录可以阶段性保留，但文档和新代码应以 Agent/Profile 命名。

## 3. 目标目录模型

### 3.1 仓库目录

```
Agent-Smith/
├── common/      # 本地基础设施：路径、SQLite、配置合并、文件工具
├── engine/      # Agent 执行内核：LLM、ReAct、技能链、记忆、安全、工具协议
├── agents/      # 内容资产库：Smith 模板、内置技能、内置工具、安全规则、插件
├── server/      # 本机后端和 CLI：会话、任务、自动化、API/SSE 编排
├── shell/       # 终端壳：Ink/React TUI，面向用户的主入口
└── docs/        # 产品、架构、执行引擎、记忆等设计文档
```

关键点：`agents/` 不是多个运行中的 Agent；它是 Agent 能力与内容的资产库。

### 3.2 运行时目录

目标模型：

```
~/.agent-smith/
├── config.yaml                 # 全局配置：LLM provider/base_url/model 等
├── agent/                      # Smith 的唯一运行时档案
│   ├── role.md                 # 身份原则，从 Smith profile seed 初始化
│   ├── style.md
│   ├── workflow.md
│   ├── toolbox.md
│   ├── context.md              # 用户偏好和长期上下文
│   ├── config.yaml             # Smith 专属覆盖配置
│   ├── memory/                 # Smith 的长期记忆
│   │   ├── recent.jsonl        # 当前实现：对话/任务摘要流水
│   │   ├── agent/              # 当前实现：个人/Agent 级记忆条目
│   │   ├── project/            # 当前实现：项目/工作区级记忆条目
│   │   ├── today.md
│   │   ├── week.md
│   │   ├── longterm.md
│   │   ├── facts.md
│   │   └── search.sqlite
│   ├── skills/                 # 用户自装/自改技能
│   ├── sessions/.state/        # 执行断点
│   └── .learner_state.json     # 偏好学习计数
├── plugins/                    # 用户安装插件
├── tool-output/                # 大工具输出落盘
├── snapshots/                  # 文件写入前快照
└── sqlite/agent-smith.sqlite   # 会话、消息、任务、自动化索引库
```

兼容现实：当前代码仍写 `~/.agent-smith/employees/<id>/`。迁移期间它应被看作 **legacy profile path**，等价映射到目标模型里的 `~/.agent-smith/agent/`，而不是目标设计本身。

## 4. 目标概念模型

| 概念 | 新定义 | 不再使用的旧心智 |
|---|---|---|
| Smith / Agent | 用户电脑上的唯一常驻执行主体 | 多个数字员工 |
| Agent Profile | Smith 的运行时档案：身份、配置、记忆、技能 | Employee instance |
| Template | 初始化 Smith 身份的出厂内容 | 可不断创建的新员工角色 |
| Skill | 工作流/SOP/领域方法论 | 子 Agent |
| Tool | 可执行能力 | 员工能力差异 |
| Session | 用户与 Smith 的一次对话线程 | 某 employee 的会话 |
| Memory | Smith 的长期经验与用户/项目事实 | 员工工作日志 |
| Knowledge | 按需注入的领域知识 | 新建角色来获得知识 |

## 5. 各层职责重定标

| 层 | 目标职责 | 命名方向 |
|---|---|---|
| `common/` | 本地基础设施，不含业务概念 | `AGENT_DIR` 替代目标路径中的 `EMPLOYEES_DIR` |
| `engine/` | Agent 执行内核，不知道 API/DB/实例管理 | 参数逐步从 `employee_dir` 改成 `agent_dir` |
| `agents/` | Smith 的内容资产库 | 保留复数目录名，但文档明确它不是实例集合 |
| `server/` | 本机守护进程和 CLI 编排层 | `AgentProfileService` 替代 `EmployeeService` |
| `shell/` | 用户界面，只面对 Smith | 类型从 `Employee` 改成 `AgentProfile` |

## 6. 记忆系统的定位调整

记忆不应该是"某个员工的工作流水"，而应该是 Smith 的长期上下文资产。

当前实现有两类内容混在一起：

1. **事件流水**：`recent.jsonl`、自动保存的 `Task/Result`，更像 episode log。
2. **耐久事实**：用户偏好、项目事实、长期工作模式，才应该稳定注入未来 prompt。

目标方向：

- `recent.jsonl` 保留为编译原料，但语义上改称 episode stream。
- `facts.md` / `longterm.md` 才是被动注入的核心。
- 自动落忆不应无筛选地把任务结果当长期记忆。
- `project` 记忆应逐步变成 workspace-scoped memory，而不是多 Agent 共享共识。

## 7. API 与数据库迁移方向

当前兼容层：

- 表：`employees`
- 外键：`employee_id`
- API：已迁移到 `/api/agent/*`
- 目录：`~/.agent-smith/employees/<id>/`

目标接口：

- 表：`agent_profile` 或直接使用固定 profile 配置，避免多实例表。
- 会话/任务：单 Smith 场景下不需要 URL 中暴露 `employee_id`。
- API：`/api/agent`、`/api/sessions`、`/api/tasks`、`/api/auto-tasks`、`/api/files`、`/api/skills`。
- 兼容层在主入口已关闭，当前只保留离线迁移记录，不再公开 `legacy` API。

## 8. 分阶段改造路线

### P0：文档定标

- 所有新文档使用 Smith / Agent Profile / Agent runtime archive。
- `employees/<id>` 只标注为 legacy compatibility。
- 停止把"新增 Agent"作为能力扩展路径。

### P1：路径适配

- 已在 `common/config.py` 增加目标常量 `AGENT_DIR = DATA_DIR / "agent"`。
- 已用 `AppPaths` / `AGENT_PROFILES_DIR` 表达语义，保留 `EMPLOYEES_DIR` 作为 legacy alias。
- 增加 `agent_dir()` helper：优先读新目录；不存在时回退到当前 Smith employee 目录。
- engine 已不再依赖入口 `sys.path` hack，并通过 package import 使用 `common` / `engine`。

### P2：服务层重命名

- 已新增 `AgentService` 作为单 Smith facade；`EmployeeService` 暂保留为 legacy 兼容服务。
- `EmployeeRepo` → `AgentProfileRepo`，底层可暂时仍读写 `employees` 表。
- shell 类型已从 `Employee` 主用迁到 `AgentProfile`。
- 错误文案已从 `Employee not found` 收敛为 `Agent profile not found`。

### P3：API 收敛

- 已新增无 `employee_id` 的 `/api/agent/...` 单 Agent API。
- 旧兼容路由已从主服务入口移除，不再作为公开 API。
- CLI 主路径对外统一为 `smith agent`，不再暴露 `employees` 命令。

### P4：数据迁移

- 将 `~/.agent-smith/employees/<smith-id>/` 迁移到 `~/.agent-smith/agent/`。
- SQLite 中 `employees` 单行迁移为 `agent_profile`，或保留兼容 view。
- `sessions.employee_id` 可改成固定 profile 引用，或在单 Agent 模型下删除外键。

## 9. 不建议做的事

- 不建议恢复多 Agent/数字员工模型。
- 不建议用多个 template 表达能力差异；能力应通过技能、工具和知识注入表达。
- 不建议一次性全仓库暴力 rename `employee`，容易破坏 API、DB、前端和迁移。
- 不建议让 `engine/` 理解 profile/DB/API；它只应接收 `agent_dir`、工具注册表、技能注册表和运行时上下文。

## 10. 当前应立刻修正的文档心智

从现在起，文档中的正式目标应写成：

```
~/.agent-smith/agent/memory/
```

而不是：

```
~/.agent-smith/employees/<id>/memory/
```

后者只能在"当前兼容实现"或"迁移前旧路径"章节出现。
