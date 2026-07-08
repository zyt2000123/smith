# Agent-Smith

本地优先的个人助手 Agent 工作台。

Smith 是你的唯一常驻 Agent，运行在本机，围绕文件、任务、记忆和工具持续工作。不是聊天机器人——是一个可执行、可积累、可扩展的终端工作台。

## 快速开始

```bash
# 安装
cd server && uv sync
cd ../shell && npm install && npm run build

# 启动终端壳
smith

# 或 CLI 模式
cd server
uv run python -m app.cli agent ensure
uv run python -m app.cli chat -m "帮我分析这段代码"
uv run python -m app.cli chat              # 交互式 REPL
uv run python -m app.cli sessions list     # 查看历史会话
```

带 LLM 配置：

```bash
AGENTSMITH_LLM_API_KEY="sk-xxx" \
AGENTSMITH_LLM_BASE_URL="https://your-api.com/v1" \
AGENTSMITH_LLM_MODEL="glm-4.7" \
cd server && uv run uvicorn app.main:app --port 8140
```

## 它能做什么

- 读写文件、执行命令、Git 操作、联网搜索和抓取
- 按任务类型自动切换工作流（debug → planning → testing → review）
- 跨会话记忆积累，越用越懂你的项目和偏好
- 17 个内置技能覆盖前端、后端、产品、测试、DevOps、数据分析等领域
- 24 条安全规则拦截危险操作
- 上下文自动压缩（两阶段：pruning + LLM 摘要），长对话不爆 token
- 文件修改前自动快照，支持 rewind

## 架构

```
server/ ──→ engine/ ──→ common/
  │                  ↑
  └──── 读取 ──→ agents/
```

| 目录 | 职责 |
|---|---|
| `common/` | 基础设施 — 配置加载、SQLite WAL、文件系统、日志 |
| `engine/` | Agent 框架 — 执行引擎、LLM 调用、记忆、技能、工具、Hook 系统、安全护栏 |
| `agents/` | 内容层 — Smith 模板、17 个技能、9 个工具、安全规则 |
| `server/` | 平台层 — FastAPI 后端 + CLI 入口 |
| `shell/` | 终端壳 — Ink/React TUI，自动拉起后端 |

四层单向依赖，不可逆。engine 不知道 FastAPI，common 不依赖任何上层。

## 核心设计

### 执行引擎

宏观确定性控制，微观 LLM 自由度：

```
用户消息
  → 任务路由（规则引擎，不用 LLM）
  → 技能链 DAG（代码控制步骤顺序 + 门禁）
  → ReAct 循环（LLM 在这里获得自由度：思考 → 调工具 → 观察）
  → 安全护栏（24 条正则规则拦截危险命令）
```

三条路由：Bug Fix（debug → planning → testing → validation → review）、Feature（planning → architecture → testing → validation → review）、Direct（跳过技能链，直接 ReAct）。

### 技能系统

两类技能，互补不冲突：

| 类型 | 数量 | 作用 | 示例 |
|---|---|---|---|
| 流程型 | 9 个 | 控制"怎么做" | planning、sde-debug、code-review、testing-strategy |
| 领域型 | 8 个 | 提供"知道什么" | frontend、backend、product、devops、testing、data-analysis |

每个技能是一个 `SKILL.md`（YAML frontmatter + Markdown），支持版本管理和 rollback。新增技能只需在 `agents/skills/` 下加目录，不改任何代码。

### Hook 系统

5 种执行模式的插件链，覆盖工具注入、prompt 修改、工具拦截等扩展点：

| 模式 | 行为 | 用途 |
|---|---|---|
| First | 第一个非空结果胜出 | 竞争式处理 |
| Series | 串行执行，无返回 | 副作用（日志、telemetry） |
| SeriesMerge | 串行合并（list concat / dict update） | 工具注入、配置合并 |
| SeriesLast | 管道：每个插件接收上一个的输出 | prompt 修改、输出后处理 |
| Parallel | 并行执行 | 清理、通知 |

内置 3 个插件：SnapshotPlugin（写文件前备份）、TruncationPlugin（大输出存文件返预览）、CompressionPlugin（裁剪旧 tool output）。

### 上下文压缩

两阶段，自动触发：

1. **Pruning**（确定性） — 反向遍历对话，保护最近 2 轮，超阈值的旧 tool output 替换为 `[pruned]`
2. **Compaction**（LLM 生成） — pruning 后仍超限，调 LLM 生成 XML 结构化摘要替换全部历史

### 记忆系统

- agent / project 双作用域（project 优先）
- Dream 整理：每 5 次对话触发，秘密过滤 → 30 天剪枝 → 70% 去重 → 模式提取
- 偏好自动学习：4 维启发式（语言/简洁度/技术水平/代码风格），同一特征观察 3 次才写入

### 文件快照

write_file 工具覆写文件前自动备份到 `~/.agent-smith/snapshots/`，支持 `rewind()` 恢复。

## 项目结构

```
Agent-Smith/
├── common/                  # 基础设施
│   ├── config.py            #   路径常量
│   ├── config_loader.py     #   四层 LLM 配置合并
│   ├── database.py          #   SQLite WAL（6 表）
│   └── filesystem.py        #   文件操作
│
├── engine/                  # Agent 执行框架
│   ├── execution/           #   任务路由 + 技能链 + ReAct + 门禁 + 回退 + 压缩
│   ├── llm/                 #   LLM 调用（OpenAI 兼容，流式 + tool_call）
│   ├── prompt/              #   11 层 System Prompt 组装
│   ├── tool/                #   工具协议 + 注册 + 输出截断
│   ├── skill/               #   技能加载 + 版本管理
│   ├── memory/              #   记忆存储 + Dream + 偏好学习
│   ├── hook.py              #   Hook 系统（5 种执行模式）
│   ├── snapshot.py          #   文件快照 + rewind
│   ├── plugin/              #   外部插件（Webhook + Polling）
│   └── safety/              #   安全护栏（24 条规则，7 类）
│
├── agents/                  # 内容定义
│   ├── templates/           #   Smith 模板（personal-assistant）
│   ├── skills/              #   17 个内置技能（9 流程型 + 8 领域型）
│   ├── tools/               #   9 个工具 provider
│   └── safety/              #   安全规则
│
├── server/                  # 平台后端
│   └── app/
│       ├── main.py          #   FastAPI 入口
│       ├── cli.py           #   CLI 入口
│       ├── routers/         #   12 个路由（薄壳）
│       ├── services/        #   11 个服务（编排层）
│       └── infrastructure/  #   Repository 持久化
│
├── shell/                   # Ink 终端壳
└── docs/                    # 设计文档
```

## 运行时数据

```
~/.agent-smith/
├── config.yaml              # 平台级配置（LLM key/url/model）
├── agents/<id>/             # Agent 实例
│   ├── role.md / ...        # 从模板复制，可编辑
│   ├── memory/              # 记忆积累
│   ├── skills/              # 自装技能
│   └── sessions/            # 会话数据
├── snapshots/               # 文件修改快照
├── tool-output/             # 截断的工具输出完整文件
└── sqlite/agent-smith.sqlite
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+ / FastAPI / uvicorn |
| Agent 引擎 | 自研（DAG + ReAct，非 LangChain） |
| 存储 | SQLite WAL + 文件系统 |
| LLM | OpenAI 兼容 API（httpx，流式 + tool_call） |
| 终端 UI | Ink (React) / TypeScript |
| 包管理 | uv (Python) / npm (shell) |

## 许可证

Private — 未开源。
