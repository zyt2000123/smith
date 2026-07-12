# Agent-Smith

本地优先、终端原生的个人 Agent 工作台。

Agent-Smith 只有一个常驻 Agent：Smith。它运行在本机，保留会话和项目上下文，按任务选择工作流，通过受控工具读写文件、执行命令、操作 Git、联网检索，并把结果交付回终端。它不是一个只负责聊天的页面，也不是多 Agent 编排平台，而是一个可以长期使用的本地执行环境。

> 当前仓库为 Private，项目仍处于持续开发阶段。

## 能做什么

- 在终端中进行交互式对话，也支持单次 CLI 调用。
- 根据任务类型选择调试、规划、重构、测试、评审等工作流。
- 通过技能和知识文档注入领域上下文，而不需要创建新的 Agent。
- 使用文件、Shell、Git、Web、待办和 MCP 工具完成实际工作。
- 在写文件前创建快照，并对危险操作执行权限和安全规则检查。
- 持久化会话、记忆和运行状态；对过长上下文执行裁剪和压缩。
- 使用 OpenAI 兼容、Anthropic 或 Gemini 模型，并按 interactive、gate、background 三类用途配置路由和超时。

## 快速开始

### 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Node.js 和 npm

### 安装

在仓库根目录执行：

```bash
cd server
uv sync

cd ../shell
npm ci
npm run build
```

只使用 CLI 时不需要构建终端壳；只需完成 `server` 的 `uv sync`。

### 配置模型

最简单的方式是使用环境变量：

```bash
export AGENTSMITH_LLM_PROVIDER=openai
export AGENTSMITH_LLM_API_KEY="sk-..."
export AGENTSMITH_LLM_BASE_URL="https://api.openai.com/v1"
export AGENTSMITH_LLM_MODEL="your-model"
```

也可以写入 `~/.agent-smith/config.yaml`：

```yaml
llm:
  provider: openai              # openai / openai_compatible / anthropic / gemini
  api_key: sk-...
  base_url: https://api.openai.com/v1
  model: your-model
  max_output_tokens: 2048
  timeout_profiles:
    interactive:
      stream_read: 120
    gate:
      read: 90
      stream_read: 90
    background:
      read: 240
      stream_read: 300
```

配置文件中的密钥不会通过配置查询接口返回；不要把本地配置文件或密钥提交到 Git。

支持的 provider：

| provider | 协议 | 适用场景 |
|---|---|---|
| `openai` / `openai_compatible` | Chat Completions | OpenAI 及兼容接口 |
| `anthropic` | Messages | Anthropic 原生接口 |
| `gemini` | Gemini 的 OpenAI 兼容接口 | Gemini 模型 |

### 启动

在终端中运行以下命令，`smith` 会使用已构建的 Ink 壳，并在需要时自动启动本地后端：

```bash
cd server
uv run smith
```

也可以直接使用 CLI：

```bash
cd server

# 初始化或检查 Smith
uv run smith agent ensure
uv run smith agent show

# 交互式对话
uv run smith chat

# 单次消息
uv run smith chat -m "帮我分析这个项目的启动流程"

# 指定工作目录并输出技能、工具和思考轨迹
uv run smith chat --workdir /path/to/project --verbose

# 查看会话
uv run smith sessions list
uv run smith sessions show SESSION_ID
```

如果需要单独启动 API 服务：

```bash
cd server
uv run uvicorn app.main:app --host 127.0.0.1 --port 8140
```

健康检查：

```bash
curl http://127.0.0.1:8140/api/health
```

默认情况下，只有健康检查公开；其他 `/api/*` 请求需要本机 Bearer Token。服务首次启动时会把 Token 保存到 `~/.agent-smith/auth_token`，终端壳会自动读取并使用它。也可以通过 `SMITH_SERVER_URL` 让终端壳连接到指定的本地服务。

## 工作方式

```text
用户
  │
  ▼
Smith（单一常驻 Agent）
  │
  ├── 任务路由：判断直接回答、调试、规划、重构或评审
  ├── 技能链：按 YAML pipeline 组织步骤和门禁
  ├── ReAct：模型在受控循环中思考、调用工具、读取结果
  ├── 安全层：权限等级、危险命令规则和事实门禁
  └── 持久化：会话、记忆、快照、工具输出和运行状态
```

宏观流程由代码和配置确定，模型只在 ReAct 环节获得执行自由度。这样既能保留 Agent 的灵活性，也能让文件修改、命令执行和长任务恢复有明确边界。

## 架构

```text
shell（Ink / React）
        │ HTTP
        ▼
server（FastAPI + CLI）
        │
        ▼
engine（执行引擎） ◄──── agents（身份、技能、工具和安全规则）
        │
        ▼
common（配置、SQLite、文件系统和日志）
```

| 目录 | 职责 |
|---|---|
| `common/` | 基础设施：路径和配置、YAML/JSON、SQLite WAL、文件系统和日志。 |
| `engine/` | 执行框架：任务路由、技能链、ReAct 循环、LLM、记忆、工具、MCP、安全、Hook 和快照。 |
| `agents/` | 内容层：Smith 身份种子、YAML 身份、pipeline、内置技能、工具 provider 和安全规则。 |
| `server/` | 平台层：FastAPI、服务编排、Agent/会话生命周期和 CLI 入口。 |
| `shell/` | 终端前端：Ink/React UI，通过 HTTP 调用后端，并负责自动拉起兼容的本地服务。 |
| `docs/` | 产品、架构、模块设计、开发规范和研究记录。 |

依赖方向保持单向：`server → engine → common`，`agents` 作为内容被 `engine` 加载，`shell` 只通过服务接口与后端通信。执行引擎不依赖 FastAPI，也不负责平台层的 Agent 实例管理。

## 关键能力

### 技能和工作流

技能以 `SKILL.md` 形式存在，使用 YAML frontmatter 描述元数据，正文提供流程、知识和判断标准。任务 pipeline 位于 `agents/pipelines/`，当前包含 Bug Fix、Feature/Refactor 等执行路径。新增工作流通常只需要新增或调整内容文件，不需要修改核心执行引擎。

### 工具和安全

工具 provider 位于 `agents/tools/`，由引擎动态发现并注册。工具定义包含参数、路径参数、写入标记和权限等级；安全层会在执行前检查危险命令、文件范围和破坏性操作。MCP 客户端支持 stdio 和 Streamable HTTP 两种传输方式。

### 记忆、快照和长上下文

- 会话消息和运行状态保存在本地 SQLite。
- Agent 和项目上下文可以通过记忆层持续积累。
- 旧的工具输出可以裁剪，完整内容保存在工具输出目录。
- 上下文过长时先做确定性裁剪，再按需生成摘要。
- `write_file` 等写操作可以在修改前创建快照，便于恢复。

## 运行时数据

默认数据目录为 `~/.agent-smith/`：

```text
~/.agent-smith/
├── config.yaml              # 平台级 LLM 配置
├── auth_token               # 本地 API Bearer Token，权限为 0600
├── agent/                   # Smith 的运行时档案、技能、记忆和配置
├── snapshots/               # 文件修改快照
├── tool-output/             # 被截断工具输出的完整文件
└── sqlite/agent-smith.sqlite
```

Smith 的内置身份和默认内容来自仓库中的 `agents/smith/`；运行时档案和用户修改保存在 `~/.agent-smith/agent/`，两者相互分离。

## 开发与验证

```bash
# Engine
cd engine
uv run --extra test pytest tests

# Server
cd ../server
uv run --extra dev pytest tests

# Shell
cd ../shell
npm test
npm run check
```

构建终端壳：

```bash
cd shell
npm run build
```

更多设计背景和模块说明见 [`docs/`](docs/) 以及：

- [`docs/01-产品设计与定位.md`](docs/01-产品设计与定位.md)
- [`docs/02-系统架构.md`](docs/02-系统架构.md)
- [`docs/04-Engine-设计与实现.md`](docs/04-Engine-设计与实现.md)
- [`docs/06-Agents-内容层.md`](docs/06-Agents-内容层.md)
- [`docs/07-Server-平台后端.md`](docs/07-Server-平台后端.md)
- [`docs/08-Shell-终端前端.md`](docs/08-Shell-终端前端.md)

## 许可证

Private — 未开源。
