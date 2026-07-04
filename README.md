# agent-Smith

> 本地Agent工作台 · 自研产品原型已落地
> 前端复用 LLM-Wiki-Knowledge-Hub 方案（React + Vite + Tailwind + shadcn/Base UI）· Agent 运行时 AgentScope · 壳 Electron
> 创建: 2026-07-03 · 状态: 产品形态收敛, 开发实现未启动

## 一句话定位

**agent-Smith 是跑在你电脑上的Agent管理与任务执行台。**

它不是一个单纯聊天窗口，也不是云端知识库的前端壳；它把 Agent 产品化成一个个可管理的「Agent」。每个Agent都有角色、人设、头像、记忆、技能、MCP/连接器、权限、任务和工作记录，并运行在本机环境里，替用户处理对话任务、自动任务和本地工具调用。

## 当前产品形态

当前原型以 QoderWake 的Agent产品形态为参考，但不复用其代码、品牌或素材；Agent-Smith 保留自己的技术栈和产品边界。

```
Agent管理
  ├─ 我的Agent / 我的群组
  ├─ 本地设备、在线状态、角色标签
  ├─ 创建对话任务 / 创建自动任务
  └─ 新建Agent

Agent详情首页
  ├─ 首页 / 项目 / 自动任务 / 任务 / 记忆 / 技能 / 连接器 / IM / 权限
  ├─ Agent身份、入职时间、简介、编辑
  ├─ 工作记录
  └─ 记忆与积累

对话任务
  ├─ 群组和会话列表
  ├─ 对话输入区、工作目录上下文
  └─ 右侧任务/能力面板：计划 / MCP / 技能 / 权限 / 知识库
```

## 产品原则

1. **Agent 是Agent，不是模型聊天框**：用户管理的是可长期存在的Agent，而不是一次性 prompt。
2. **本地优先**：人格、记忆、会话、本地工具、任务执行上下文都属于用户电脑；云端只提供团队知识和共享能力。
3. **任务优先于闲聊**：入口围绕对话任务、自动任务、任务列表、工作记录组织，而不是做泛聊天社区。
4. **能力显式可控**：技能、MCP、知识库、权限要在当前任务上下文里看得见、可切换、可关闭。
5. **工作过程可追踪**：Agent首页必须有工作记录、入职信息、记忆与积累，避免 Agent 变成不可审计的黑箱。

## 与 AI Knowledge Hub 的边界

| | agent-Smith（本地） | AI Knowledge Hub（云端） |
|---|---|---|
| 定位 | Agent、任务、记忆、本地工具、权限 | 团队知识库、Wiki、权限、检索、MCP token |
| 数据归属 | 个人电脑（`~/.agent-smith`） | 团队服务器 |
| 核心对象 | Agent / 任务 / 技能 / 连接器 / 记忆 | 知识库 / 文档 / Wiki / 用户权限 |
| 集成方式 | 调用 Hub MCP 或检索 API | 提供 MCP 工具和来源回链 |
| 不做什么 | 不承载团队知识管理 | 不再扩多 Agent 雇佣层 |

## 技术方向

```
SwiftUI macOS 原生应用
  │ HTTP + SSE（URLSession）
  ▼
Python 本地 server（FastAPI + AgentScope）
  ├─ Agent运行时
  ├─ 本地文件/SQLite 存储
  ├─ 本地工具执行
  └─ Hub MCP / 检索 API 连接
```

## 项目结构

| 目录 | 内容 |
|---|---|
| `macos-app/AgentSmith/` | SwiftUI macOS 前端（Swift Package，19 个源文件） |
| `prototype/` | 早期 React Web 原型（已归档，不再主力开发） |
| `docs/` | 产品设计、架构、路线图、竞品调研 |

## 文档索引

| 文档 | 内容 |
|---|---|
| [docs/01-产品设计.md](docs/01-产品设计.md) | 产品定位、信息架构、核心场景、MVP 边界 |
| [docs/02-架构与借鉴.md](docs/02-架构与借鉴.md) | 技术架构、参考对象、实现边界、风险 |
| [docs/03-与知识库的拆分与集成.md](docs/03-与知识库的拆分与集成.md) | 与 AI Knowledge Hub 的职责拆分和集成契约 |
| [docs/04-开发路线图.md](docs/04-开发路线图.md) | 分阶段研发路线和验证点 |
| [docs/05-QoderWake技术调研.md](docs/05-QoderWake技术调研.md) | QoderWake 技术栈深度调研（网络 + 逆向工程） |
| [docs/06-Agent文件与技能系统设计参考.md](docs/06-Agent文件与技能系统设计参考.md) | Agent身份文件、技能打包、安全护栏设计参考 |
| [docs/07-QoderWake完整产品逆向.md](docs/07-QoderWake完整产品逆向.md) | 完整产品逆向（架构、Agent 执行模型、门禁、技能、安全、API 全景） |
| [docs/08-QoderWake前端架构分析.md](docs/08-QoderWake前端架构分析.md) | 前端 JS bundle 反编译分析 |
| [macos-app/AgentSmith](macos-app/AgentSmith) | SwiftUI macOS 前端原型 |

