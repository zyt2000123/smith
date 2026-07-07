# 05 · QoderWake 技术调研

> 调研时间：2026-07-03
> 方法：网络多源调研 + 本地逆向工程（`~/.qoderwake/` 二进制分析、JS bundle 分析、SQLite schema 分析、文件结构分析）
> 目的：为 Agent-Smith 产品设计和架构决策提供参考

## 产品概况

QoderWake 是阿里巴巴旗下 Qoder 团队（国内品牌：通义灵码）于 2026 年 5 月推出的 AI Agent 平台。与传统 AI 编码助手不同，它部署的是名为 Waker 的持久化 AI 智能体。每个 Waker 有名字、入职日期、工作记录，能 24/7 自主运作。

- 官网：qoder.com/qoderwake
- 文档：docs.qoder.com/qoderwake/overview
- GitHub：github.com/QoderAI（23 个公开仓库，核心闭源）
- 法律实体：Bright Zenith Private Limited（新加坡）
- 宣称数据：500 万+用户，ARR 超 6000 万美元

### Qoder 产品家族

| 产品 | 定位 | 架构 |
|---|---|---|
| Qoder IDE | AI 编码 IDE | Electron（VS Code / Code-OSS 分支） |
| QoderWork | AI 桌面助手 | 闭源，.dmg/.exe 分发 |
| QoderWake | AI Agent 平台 | 本地 daemon + 浏览器 Web Console |
| Qoder Remote Control | 移动端伴侣 | iOS/Android，框架未确定 |

## 完整技术架构

```
+--------------------------------------------------+
|           QoderWake 技术架构                       |
+--------------------------------------------------+
|                                                    |
|  [macOS 菜单栏]  Swift / AppKit (647KB)            |
|       |                                            |
|       v                                            |
|  [守护进程]  定制 Bun v1.3.14 (Zig + JSC)  110MB   |
|       |                                            |
|       +---> [Web Console]  React + Vite            |
|       |     Tailwind CSS v4.1.18 + Ant Design      |
|       |     SWR / Marked / Mermaid / Shiki / KaTeX |
|       |                                            |
|       +---> [存储层]  SQLite (76表, WAL模式)        |
|       |     sqlite-vec 向量搜索                     |
|       |     Git 版本化 (Memory/Skills)              |
|       |     Markdown 身份文件                       |
|       |                                            |
|       +---> [MCP 端点]  SSE @ localhost:19820      |
|       |                                            |
|       +---> [CLI 客户端]  Bun v1.3.14  96MB        |
|       |     ACP = JSON-RPC 2.0 over stdio          |
|       |                                            |
|       +---> [插件触发器]  Python                    |
|       |     DingTalk / Aone / GitHub Webhooks       |
|       |                                            |
|       +---> [浏览器扩展]  Chrome Manifest V3        |
|             nativeMessaging + localhost HTTP        |
|                                                    |
|  [LLM]  Qwen3.7 / DeepSeek-V4 / GLM-5.2 /        |
|          Kimi-K2.7 / MiniMax-M3 (仅国产)           |
|                                                    |
|  [移动端]  iOS + Android (框架未确定)               |
|                                                    |
+--------------------------------------------------+
```

## 逐维度详情

### 1. 桌面端框架

**结论：Swift 原生菜单栏壳 + Bun 守护进程 + 浏览器 Web Console。非 Electron，非 Tauri。**

| 组件 | 技术 | 大小 | 作用 |
|---|---|---|---|
| `QoderWake.app` | Swift / AppKit | 647 KB | 菜单栏启动器、登录项管理、守护进程生命周期 |
| `~/.qoderwake/qoderwake` | 定制 Bun v1.3.14（Zig + JavaScriptCore） | 110 MB | 主守护进程，监听 127.0.0.1:19820 |
| `~/.qoderwake/qodercli/qodercli-wake` | 定制 Bun v1.3.14 | 96 MB | CLI 客户端 |

逆向证据：

- `file` 命令确认 Mach-O 64-bit arm64
- `strings` 输出包含 `Bun::`、`Zig::GlobalObject`、`BunString`、`BunJSCModule.h` 等标识
- `otool -L` 仅链接系统库（libicucore、libresolv、libc++、libSystem），无 Electron 痕迹
- Info.plist Bundle ID 为 `com.qoder.QoderWake.MenuBar`
- `~/.qoderwake/resources/build-info/bun_version` = `1.3.14`

安装方式：`curl -fsSL https://qoder-ide.oss-ap-southeast-1.aliyuncs.com/qoderwake/install.sh | bash`

### 2. 前端

**结论：React + Vite + Tailwind CSS v4.1.18 + Ant Design (antd)**

| 维度 | 技术 | 逆向证据 |
|---|---|---|
| UI 框架 | React | `<div id="root">`；JS bundle 中 8225 处 `jsx`、905 处 `useState`、460 处 `useEffect` |
| 构建工具 | Vite | JS bundle 以 `const __vite__mapDeps=...` 开头；`<script type="module">` |
| CSS 框架 | Tailwind CSS v4.1.18 | CSS 文件头注释 `/*! tailwindcss v4.1.18 */` |
| 组件库 | Ant Design (antd) | CSS 中 1078 个 `.ant-` 前缀选择器 |
| 数据获取 | SWR | bundle 中存在 `swr` 标识 |
| Markdown 渲染 | Marked | 24 处出现 |
| 图表/流程图 | Mermaid + D3 | 独立 chunk `mermaid-59c9be08-BY4qcIhF.js` |
| 语法高亮 | Shiki | 包含数十种语言语法 chunk |
| 数学公式 | KaTeX | 独立 chunk `katex-uyQzrBQ9.js` |

主 bundle 约 3.8 MB（未压缩）。

### 3. 后端 / Agent 运行时

**结论：定制 Bun v1.3.14（Zig + JavaScriptCore），自研 Harness-First Agent 框架。非 AgentScope / LangChain。**

运行时：

- 核心是定制的 Bun 分支，使用 JavaScriptCore（WebKit JS 引擎），而非 V8
- Zig 编译的原生二进制，静态链接 JSC
- 内嵌 Node.js 兼容层（`node:fs`、`node:http2`、`node:crypto` 等）
- npm 包 `@qoder-ai/qodercli`，已发布 160 个版本

Agent 框架（Harness-First Architecture）：

- **Orchestrator**（编排器）：计划和流程控制
- **Executor**（执行器）：意图理解和复杂推理
- **Session Ledger**（会话账本）：独立日志，记录所有操作和状态，崩溃后可恢复
- **双层验证**：执行器自检 + 独立验证器复核，失败自动回退重做
- **Critic-Refiner 机制**：任务完成后审查冗余步骤和判断偏差，生成结构化学习信号

五维经验存储：

1. Memory — 项目上下文、编码风格、操作历史
2. Skills — 原子化可复用能力
3. Strategy — 复杂场景决策蓝图
4. Validation Rules — 质量门禁
5. Workflows — 端到端流程映射

与 AgentScope 无技术关联（尽管同出阿里）。

### 4. LLM 模型支持

**结论：仅支持国产大模型提供商。不支持 OpenAI 和 Anthropic。**

内置模型层级（通过 Qoder 积分）：

| 层级 | 模型 |
|---|---|
| Ultimate | Qwen3.7-Max |
| Performance | Qwen3.7-Plus、DeepSeek-V4-Pro |
| Efficient | DeepSeek-V4-Flash、GLM-5.2、Kimi-K2.7-Code |
| Lite | MiniMax-M3 |
| Auto | 智能路由自动选择 |

BYOK 支持（仅 Qoder IDE/CLI 个人版）：阿里云百炼、DeepSeek、Z.ai、Kimi、MiniMax、小米 MIMO。

QoderWake 目前完全没有自定义模型支持，forum.qoder.com 上有活跃功能请求。

### 5. 本地存储

**结论：SQLite（WAL 模式）+ sqlite-vec 向量扩展 + Git 版本化 + Markdown 身份文件的混合架构。**

核心数据库：`~/.qoderwake/data/store/qoderwake.sqlite`（约 3.7MB），76 张表，32 次 schema 迁移。

关键表按功能域：

| 功能域 | 关键表 | 架构模式 |
|---|---|---|
| Agent/会话 | agents, sessions, session_events | 有序事件流 |
| 通用 KV | storage_records, storage_logs | 域分区 KV + 追加式审计 |
| 技能 | skills | 每个 Agent 注册的技能 |
| 多 Agent 协作 | team_groups_v3, team_group_messages_v3 | 团队消息 |
| 任务规划 | missions, mission_events, plan_proposals, plan_tasks | 事件溯源状态机 |
| 触发器 | triggers, trigger_runs, tasks | 定时/webhook/轮询 |
| 工作流 | workflow_definitions, workflow_runs, workflow_events | 版本化工作流 |
| 知识（QMind） | qmind_knowledge_bindings, qmind_knowledge_mutations | Agent-知识绑定 |
| 可观测性 | task_traces, task_trace_events, board_task_projection | 分布式追踪 |

向量搜索：`~/.qoderwake/resources/sqlite-vec/vec0.dylib`（SQLite 扩展）。

Git 版本化：每个 Worker 下有独立 git 仓库管理 Memory 和 Skill 的版本历史，共 18 个 git 仓库。提交消息格式如 `qoderwake memory snapshot memory_initialize`、`qoderwake skill version common-software-developer-planning install`。

架构模式：

- 事件溯源状态机：mission/planning/team 使用 `payload_json` 载体
- 事务性发件箱：`event_delivery_outbox` 确保至少一次事件投递
- Git-as-versioning-backend：Memory 和 Skill 内容使用 git 管理历史和回滚
- 域分区 KV：`storage_records` 按 domain 灵活分区

### 6. 通信协议

**结论：HTTP/REST + SSE + ACP（JSON-RPC 2.0 over stdio）。无 WebSocket / gRPC。**

| 场景 | 协议 |
|---|---|
| Web Console <-> Daemon | HTTP + SSE，localhost:19820 |
| Cloud Agents API | HTTP/REST + Bearer Token + SSE 流 |
| CLI <-> Agent | ACP = JSON-RPC 2.0 over stdio (NDJSON) |
| 浏览器扩展 <-> Daemon | Chrome nativeMessaging + localhost HTTP |
| 内置 MCP 端点 | SSE @ `http://127.0.0.1:19820/api/internal/builtin-mcp/...` |

### 7. MCP 支持

**结论：完整支持四种传输方式，守护进程自身也暴露 MCP 端点。**

| 传输类型 | 说明 |
|---|---|
| STDIO | stdin/stdout，本地工具和 CLI 集成 |
| SSE | HTTP POST 请求 + 事件流响应 |
| Streamable HTTP | 与 SSE 同配置，自动检测 |
| SDK | 进程内 MCP 服务器，`createSdkMcpServer()` + Zod schema |

守护进程暴露内置 MCP 端点如 `qoderwake_memory`，通过 SSE 在 `http://127.0.0.1:19820/api/internal/builtin-mcp/` 提供服务。支持 OAuth 2.0 认证的 MCP Connectors，v0.0.21 新增 connector 自动恢复。

### 8. 技能/插件系统

**结论：三层扩展体系 — Skills / Plugins / Connectors。**

| 类型 | 打包格式 | 存储位置 |
|---|---|---|
| Skill | `SKILL.md`（YAML frontmatter + Markdown 指令） | `~/.qoderwake/data/workers/<id>/.qoder-plugin/skills/*/SKILL.md` |
| Plugin | 目录 + `.qoder-plugin/plugin.json` + `skills/` + 可选 `agents/`、`.mcp.json` | `~/.qoderwake/plugins/` |
| 内置 Skill | `SKILL.md` + prompt 文件 | `~/.qoderwake/resources/builtin-skills/` |
| Connector | OAuth 2.0 HTTPS MCP Server | 远程 |

SKILL.md 格式：

```yaml
---
name: my-skill-name
description: "技能描述"
version: "1.0.0"
---
# Markdown 正文 = AI 执行指令
```

- Marketplace 技能只读且受保护
- 自进化技能（Self-evolving）允许 Waker 在使用中修改
- 社区贡献通过 GitHub PR 到 `Qoder-AI/qoder-community`
- 安全护栏：`~/.qoderwake/resources/security/tool-guard-rules/dangerous_shell_commands.json`

### 9. Worker 本地文件结构

逆向确认：

```
~/.qoderwake/data/workers/<agent-id>/
  .qoder/
    IDENTITY.md          # Agent 身份：谁，负责什么
    PERSONA.md           # 工作风格、表达方式、边界
    BIBLE.md             # 工作流、操作规范、验收标准
    TOOLS.md             # 工具配置
    USER.md              # 用户偏好
    MEMORY.md            # 记忆
  .qoder-plugin/
    plugin.json          # 插件配置
    hooks/hooks.json     # 钩子
    skills/*/SKILL.md    # 技能（YAML frontmatter + Markdown）
    skills/*/events.jsonl     # 技能事件日志
    skills/*/manifests/*.json # 技能清单
  sessions/<session-id>/ # 会话运行时数据
  workspace/             # 工作目录
```

### 10. 工作模式

三大工作模式 + 自定义 Skills：

| 模式 | 定位 |
|---|---|
| Ask | 问答模式，快速回答 |
| Agent | 自主执行模式，自动规划和完成任务 |
| Quest | 任务探索模式，复杂多步任务 |
| 自定义 Skills | 用户定义的原子化能力 |

多 Agent 编排通过 WakerFlow 引擎：复杂任务分解为多个 Phase，Leader Waker 协调其他 Waker 执行。

### 11. 安全设计

- 本地虚拟环境执行，只访问用户授权文件夹
- 数据不上传云端
- 删除文件移动到受保护恢复区，非永久删除
- 红线/边界机制：用户定义可为与不可为边界，越界暂停请求审批
- `dangerous_shell_commands.json` 护栏文件

### 12. 定价

捆绑在 Qoder 订阅中，一个订阅覆盖 Qoder / QoderWork / QoderWake：

| 方案 | 价格 | 月度积分 |
|---|---|---|
| Community | 免费 | 2 周 Pro 试用 + BYOK |
| Pro | $20/月 | 2,000 |
| Pro+ | $60/月 | 6,000 |
| Ultra | $200/月 | 20,000 |

额外积分 $0.02/积分，非高峰时段消耗打折（Qwen3.7-Max 省 80%，Plus 省 60%）。

### 13. 开源组件

GitHub QoderAI 组织 23 个公开仓库，核心闭源。

| 仓库 | 语言 | 说明 |
|---|---|---|
| qoder-action | JS / Shell | GitHub Action，OIDC 认证 |
| qoder-acp-demos | TypeScript | ACP 协议演示，确认 JSON-RPC 2.0 |
| qoder-community | Astro / TypeScript | 社区技能平台，Cloudflare Pages |
| cloud-agents-sdk-go | Go | Cloud Agents Go SDK（空仓库） |
| homebrew-qoder | Ruby | Homebrew 安装配方 |

第三方发现：

- numtide/llm-agents.nix：Nix 包定义揭示 Bun 运行时捆绑
- x1xhlol/system-prompts-and-models-of-ai-tools/Qoder：泄露的系统提示词
- npm `@qoder-ai/qodercli`：160 个版本，70.5MB，Node.js >= 20.0.0

## 对 Agent-Smith 的启示

| QoderWake 方案 | Agent-Smith 现有计划 | 启示 |
|---|---|---|
| Swift 菜单栏壳 (647KB) + daemon | Electron 或 daemon + 浏览器 | 原生壳极轻，Phase 0 可 spike |
| React + Vite + Tailwind + antd | React + Vite + Tailwind + shadcn | 技术路线一致，验证方向正确 |
| IDENTITY.md / PERSONA.md / BIBLE.md | role.md / style.md / workflow.md | 设计完全吻合 |
| SQLite 76 表 + 事件溯源 | 文件 + SQLite | 可先简单后复杂，事件溯源是演进方向 |
| sqlite-vec 本地向量搜索 | Hub 提供检索 | 本地 RAG 是可选升级路径 |
| Git 版本化 Memory/Skills | 文件系统 | Git 管理记忆版本是低成本好方案 |
| SKILL.md（YAML + Markdown） | 待定 | 可直接参考此格式 |
| Python 触发器 | Python server | Python 选择完全可行 |
| Ask / Agent / Quest 三模式 | 对话任务 / 自动任务 | 可参考增加 Quest 探索模式 |
| dangerous_shell_commands.json | 工具白名单 | 安全护栏文件是好实践 |

## 未确定项

| 维度 | 状态 | 原因 |
|---|---|---|
| 移动端 App 框架 | 未知 | 本机无 APK，需下载后拆包分析 |
