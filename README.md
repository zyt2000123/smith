# Agent-Smith

> 本地数字员工工作台 — 在你的电脑上雇佣、管理和调度 AI 数字员工

## 产品定位

Agent-Smith 把 AI Agent 产品化为可管理的「数字员工」。每个数字员工有角色、人设、记忆、技能、权限和工作记录，运行在本机环境中，替用户处理对话任务、自动任务和本地工具调用。

**不是聊天机器人，不是云端壳**——用户管理的是可长期存在的员工，而不是一次性 prompt。

## 架构总览

五层分离，单向依赖：

```
app/  ── HTTP/SSE ──→  server/  ── import ──→  engine/  ── import ──→  common/
                                │                        ↑
                                └──── 读取 ────→  agents/ ┘
```

| 目录 | 职责 | 语言 |
|---|---|---|
| `common/` | 公共基础设施（配置、SQLite、文件系统、日志） | Python |
| `engine/` | 自研 Agent 框架（LLM 调用、DAG+ReAct 执行引擎、记忆、安全护栏） | Python |
| `agents/` | Agent 内容定义（8 个角色模板、6 个内置技能、9 个工具、24 条安全规则） | .md/.yaml/.json + Python |
| `server/` | 平台后端（FastAPI，员工/会话/任务/团队管理，23+ API 端点） | Python |
| `app/` | 原生前端（深蓝主题 Codex 风格） | Swift 6.1 / SwiftUI / macOS 15+ |

## 快速开始

### 后端

```bash
cd server && uv sync
uv run uvicorn app.main:app --port 8140 --reload
```

带 LLM 配置启动：

```bash
AGENTSMITH_LLM_API_KEY="sk-xxx" \
AGENTSMITH_LLM_BASE_URL="https://your-api.com/v1" \
AGENTSMITH_LLM_MODEL="glm-4.7" \
uv run uvicorn app.main:app --port 8140
```

### macOS 前端

需要 Xcode 16+，在 Xcode 中打开 `app/Package.swift` 并构建运行。

## 项目结构

```
Agent-Smith/
├── common/                  # 基础设施层
│   ├── config.py            #   路径常量 (DATA_DIR, TEMPLATES_DIR, ...)
│   ├── config_loader.py     #   四层 LLM 配置合并
│   ├── database.py          #   SQLite WAL + 6 表 schema
│   ├── filesystem.py        #   员工目录操作
│   ├── log.py               #   日志
│   └── yaml_utils.py        #   YAML/JSON 读写
│
├── engine/                  # Agent 执行框架
│   ├── execution/           #   四层执行引擎
│   │   ├── task_router.py   #     第 1 层：任务路由（规则引擎）
│   │   ├── skill_chain.py   #     第 2 层：技能链 DAG 编排
│   │   ├── agent_loop.py    #     第 3 层：ReAct 循环
│   │   ├── gate.py          #     12 个门禁
│   │   └── backtrack.py     #     回退 + Failure Loop Guard
│   ├── llm/                 #   LLM 调用（OpenAI 兼容 + 流式 + tool_call）
│   ├── prompt/              #   12 层 System Prompt 组装
│   ├── tool/                #   工具协议 + 注册 + JSON Schema
│   ├── skill/               #   技能加载 + 注册 + 执行 + 版本管理
│   ├── memory/              #   记忆存储 + Dream 整理 + 偏好学习
│   ├── plugin/              #   插件系统（Webhook + Polling）
│   └── safety/              #   工具调用安全拦截
│
├── agents/                  # Agent 内容定义
│   ├── templates/           #   8 个角色模板（只读，Git 跟踪）
│   ├── skills/              #   6 个内置技能 (SKILL.md)
│   ├── tools/               #   9 个工具 provider
│   ├── plugins/             #   插件（GitHub webhook）
│   ├── safety/              #   24 条安全规则（7 大类）
│   └── output_style.md      #   输出格式规范
│
├── server/                  # 平台后端
│   └── app/
│       ├── main.py          #   FastAPI 入口
│       ├── domain/          #   领域模型
│       ├── routers/         #   12 个路由模块
│       ├── services/        #   11 个业务服务
│       ├── infrastructure/  #   Repository 持久化
│       └── utils/           #   工具（cron 解析等）
│
├── app/                     # macOS 原生前端
│   ├── Package.swift        #   SPM 包定义
│   └── Sources/AgentSmith/
│       ├── ContentView.swift        # 主布局（侧栏 + 内容区）
│       ├── Components/              # 设计系统（AppPalette, AppTypography）
│       ├── Models/Employee.swift    # 数据模型
│       ├── Services/APIClient.swift # HTTP 客户端
│       └── Views/                   # 页面视图
│
└── docs/                    # 设计文档
```

## 核心概念

### 数字员工

从角色模板创建，拥有独立的人格、技能、记忆和权限。模板在 `agents/templates/` 中定义（只读），创建时复制到 `~/.agent-smith/employees/<id>/`（可读写），此后独立运行、独立积累。

### 执行引擎

混合 DAG + ReAct 四层架构：

1. **任务路由**（规则引擎）— 分为 Bug Fix / Feature / Direct 三条路由
2. **技能链 DAG**（代码控制）— 强制执行步骤顺序和门禁
3. **ReAct 循环**（LLM 控制）— 每个技能节点内的思考-工具-观察循环
4. **安全护栏**（正则拦截）— 24 条规则，7 大类危险命令拦截

宏观流程由代码确定性控制，LLM 只在 ReAct 循环内获得自由度。

### LLM 配置

四层覆盖，优先级从低到高：环境变量/平台级 → 模板级 → 员工级 → 会话级。

### 新加 Agent

```bash
mkdir agents/templates/<role-name>/
# 填写 role.md, style.md, workflow.md, toolbox.md, config.yaml
# 可选：expertise.json, traits.json, pipeline.json, context.md
# server 自动扫描发现新模板，无需改任何代码
```

## 运行时数据

```
~/.agent-smith/
├── config.yaml                    # 平台级配置
├── employees/<id>/                # 员工实例
│   ├── role.md / style.md / ...   # 从模板复制，可编辑
│   ├── memory/                    # 运行时记忆积累
│   ├── skills/                    # 员工自装技能
│   └── sessions/                  # 会话数据
├── plugins/                       # 用户安装的插件
└── sqlite/agent-smith.sqlite      # 索引库（WAL 模式）
```

## 文档索引

| 文档 | 内容 |
|---|---|
| [docs/01-产品设计与定位](docs/01-产品设计与定位.md) | 产品定位、目标用户、核心场景、产品支柱、MVP 边界 |
| [docs/02-系统架构](docs/02-系统架构.md) | 五层架构、依赖方向、分层职责、变更影响矩阵 |
| [docs/03-Agent执行引擎](docs/03-Agent执行引擎.md) | 四层执行模型、门禁系统、回退机制、Prompt 组装 |
| [docs/04-后端API参考](docs/04-后端API参考.md) | FastAPI 全部端点、领域模型、服务层设计 |
| [docs/05-macOS前端架构](docs/05-macOS前端架构.md) | SwiftUI 视图层级、设计系统、状态管理、API 集成 |
| [docs/06-Agent模板与技能规范](docs/06-Agent模板与技能规范.md) | 模板文件格式、SKILL.md 规范、工具 Provider 接口、安全规则 |
| [docs/07-开发规范与约定](docs/07-开发规范与约定.md) | 分层规则、命名约定、代码风格、提交规范 |
| [docs/08-开发路线图](docs/08-开发路线图.md) | 分阶段研发计划、当前进度、后续能力 |
| [docs/09-TODO-待优化清单](docs/09-TODO-待优化清单.md) | 待实现功能、待检查项、技术债务 |
| [docs/reference/](docs/reference/) | 竞品调研（QoderWake 逆向、OpenHanako 调研、前端分析） |

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | Python 3.11+ / FastAPI / uvicorn |
| Agent 引擎 | 自研（DAG + ReAct，非 AgentScope/LangChain） |
| 数据存储 | SQLite (WAL) + 文件系统 |
| LLM 调用 | OpenAI 兼容 API（httpx，支持流式 + tool_call） |
| 前端 | Swift 6.1 / SwiftUI / macOS 15+ |
| 包管理 | uv (Python) / SPM (Swift) |

## 许可证

Private — 未开源。
