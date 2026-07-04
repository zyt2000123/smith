# 08 · QoderWake 前端架构分析

> 来源：前端 JS bundle 反编译（2026-07-03）
> 主 bundle：3.7MB（Vite 构建），知识库模块 620KB 独立 chunk，80+ Shiki 语言 chunk 按需加载

## 技术栈

| 层 | 技术 |
|---|---|
| UI 框架 | React（useState 905 处、useEffect 460、useCallback 407、useMemo 353、useRef 296） |
| 构建工具 | Vite（Bun 构建） |
| CSS | Tailwind CSS v4.1.18 |
| 组件库 | Ant Design（Upload、Input 等，1078 个 .ant- 选择器） |
| 富文本 | Tiptap（基于 ProseMirror，用于 Memory/知识编辑） |
| 代码高亮 | Shiki（80+ 语言按需加载） |
| Markdown | marked + remark 插件链 |
| 图表 | Mermaid + D3 |
| 数学公式 | KaTeX |
| 路由 | React Router |
| 状态管理 | 自建 store（getState/setState/subscribe，类 Zustand 但内建）+ 7 个 createContext |
| 数据获取 | 自建 request() 封装（~180+ 个服务方法），无 SWR/React Query |
| 实时通信 | EventSource（SSE，出现 43 次） |
| i18n | 内建系统（非 react-i18next），支持 zh-CN / en-US / ja |
| 主题 | 亮/暗切换，createFromRawTheme |

## 状态管理

无第三方状态库。自建 store 模式：多个 store 对象暴露 `getState()` / `setState()` / `subscribe()`，7 个 `createContext` 用于局部共享。

## SSE 实时更新

- 全局事件流：`/api/console/events/stream`
- 会话级：`/api/sessions/${id}/events/stream`
- 重连（revive）、已读标记、可见性感知去抖

## 代码分割

| Bundle | 大小 | 内容 |
|---|---|---|
| 主 bundle | 3.7MB | 全部核心功能 |
| knowledge_routes.js | 620KB | 知识库模块 |
| worker_knowledge.js | 16.5KB | Worker 知识模块 |
| Shiki 语言 chunks | 各几 KB | 80+ 种语言语法（按需） |

## 完整路由树

```
/management                        → Waker 管理列表
/wakers/new                        → 新建 Waker
/wakers/:workerId/
  ├── home                         → 概览仪表盘
  ├── project                      → 项目管理
  ├── triggers                     → 自动化/触发器
  ├── triggers/new | :id | :id/edit
  ├── skill                        → 技能管理
  ├── mcp                          → MCP 连接器
  ├── knowledge                    → 知识库
  ├── connector                    → 外部连接器
  ├── im | im/:channelId/edit      → IM 渠道
  ├── permissions                  → 权限管理
  ├── memory                       → 记忆（MEMORY.md）
  └── task                         → 任务列表

/conversations/new                 → 新建对话
/conversations/:sessionId          → 对话详情
/conversations/:sessionId/debug    → 对话调试

/wakerflow                         → 工作流列表
/wakerflow/:workflowId             → 详情（diagram/script 双视图）
/wakerflow/:workflowId/runs/:runId → 运行详情

/board                             → 任务看板（泳道/列表）
/board/human-actions               → 人工审批队列

/knowledge                         → 知识库首页
/knowledge/notebooks/:id           → 笔记本
/knowledge/featured/:id            → 精选知识

/projects/public                   → 公开项目
/teams/group-conversations/:groupId/chat → 团队群聊
/missions/:missionId               → 任务详情
/missions/:missionId/audit         → 任务审计
/extensions                        → 扩展管理

/settings/preferences              → 偏好（主题/语言）
/settings/environments             → 环境变量
/settings/personal-access-tokens   → PAT
```

## 关键数据模型

| 实体 | ID 字段 | bundle 中出现次数 |
|---|---|---|
| Workflow | workflow_id | 940 |
| Skill | skill_id | 592 |
| Session | session_id | 550+ |
| Trigger | trigger_id | 485 |
| Project | project_id | 478 |
| Agent/Waker | agent_id / worker_id | 460+ |
| Team | team_id | 435 |
| Connector | — | 227 |
| Notebook | notebook_id | 89+ |
| Mission | mission_id | 71 |

## 安全/权限（前端侧）

- fileGuard：文件访问守卫
- toolGuard：工具调用守卫
- modelSecurity：模型安全
- permission + approval：权限审批（pending → resolve）
- accessPolicy：IM Bot 访问策略
- consent：用户授权同意

## 遥测

179 个追踪事件，覆盖所有用户交互路径，`/api/telemetry/events` 上报。

## 对 Agent-Smith 的启示

| QoderWake | 建议 |
|---|---|
| 自建 store（类 Zustand） | 直接用 Zustand（更简单，生态好） |
| 自建 request() + 180+ 方法 | 可用 SWR 替代（自动缓存、重试） |
| Tiptap 富文本 | 记忆编辑需要时再引入 |
| Shiki 80+ 语言按需加载 | 代码高亮按需模式值得参考 |
| 内建 i18n | v0 中文优先，暂不需要 |
| Ant Design | Agent-Smith 用 shadcn，风格更轻 |
