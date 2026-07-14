# 08 · Shell 终端前端

## 模块定位

`shell/` 是 Agent-Smith 的终端原生前端（terminal-native frontend）。它基于 Ink（React for CLI）构建，在终端中提供富交互 UI，让用户与 Smith agent 实时对话。

架构边界：

- Shell 仅通过 HTTP/SSE 与 `server/` 通信，**从不 import engine/ 或 common/**。
- Shell 不包含任何业务逻辑——它是纯展示层和用户交互层。
- 后端进程管理由 Shell 自行处理：启动时自动探测或拉起本地 Python 后端。

```
用户终端
  ↕
shell/ (Ink/React, TypeScript)
  ↕  HTTP + SSE
server/ (FastAPI, Python)
  ↕
engine/ → common/
```

---

## 技术栈

| 项目 | 说明 |
|------|------|
| 包名 | `smith-shell` |
| 版本 | `0.2.1` |
| 运行时 | Node.js (ES2022 target) |
| 模块系统 | ESM (`"type": "module"`) |
| 渲染框架 | Ink 7 (`ink@^7.1.0`) |
| UI 框架 | React 19 (`react@^19.2.0`) |
| 状态管理 | Zustand 5 (`zustand@^5.0.14`) |
| Markdown 渲染 | `@assistant-ui/react-ink-markdown@^0.0.30` |
| 加载动画 | `ink-spinner@^5.0.0` |
| 文本输入 | `ink-text-input@^6.0.0` |
| 类型检查 | TypeScript 5.9 (`strict: true`) |
| 格式化/检查 | Biome (`@biomejs/biome@^2.5.2`) |
| 构建目标 | ES2022, ESNext modules, Bundler resolution |
| JSX 转换 | `react-jsx` (自动 JSX 运行时) |

### npm scripts

| 命令 | 说明 |
|------|------|
| `npm run build` | `tsc -p tsconfig.build.json`，输出到 `dist/` |
| `npm run check` | Biome 检查 `src/` |
| `npm run format` | Biome 格式化 `src/` |
| `npm run test` | 先 tsc 类型检查，再运行 `scripts/run-tests.mjs` |

---

## 架构概览

### 源文件清单

| 文件 | 职责 | 类型 |
|------|------|------|
| `index.tsx` | 入口，组件树根，CLI 渲染 | React 组件 |
| `bridge.ts` | 后端桥接层，所有 API 调用的中介 | 类 |
| `api.ts` | HTTP/SSE 客户端，类型定义 | 纯函数 |
| `store.ts` | Zustand 全局状态 store | 纯函数 |
| `hud.tsx` | 状态栏组件（HUD） | React 组件 |
| `transcript.tsx` | 对话渲染，stream 事件映射 | React 组件 + 纯函数 |
| `commands.ts` | 斜杠命令注册和执行 | 纯函数 |
| `input.ts` | 键盘输入处理 | React Hook |
| `activity.ts` | 工具调用活动追踪 | 纯函数 |
| `output.ts` | 输出文本处理（emoji 清理） | 纯函数 |
| `setup.ts` | 初始配置向导 | 纯函数 |
| `conversation.ts` | 会话重置工厂 | 纯函数 |
| `dev-server.ts` | 本地后端自动启动 | 纯函数 |

### 组件树

```
SmithApp                          ← 顶层组件
├── 头部：Agent-Smith v0.2.1
├── ShellContent                  ← 主内容区
│   ├── [mode=boot]  Spinner + "Booting..."
│   ├── [mode=setup] HeroPanel + SetupPanel
│   └── [mode=chat]
│       ├── HeroPanel             ← ASCII art logo
│       ├── welcomeNotice         ← 可选通知
│       ├── PluginsPanel          ← /plugins 面板
│       ├── SkillsPanel           ← /skills 面板
│       ├── SessionsPanel         ← /sessions 面板
│       └── Transcript            ← 对话记录
│           ├── SystemMessage     ← 系统消息
│           └── TurnViewWithMode  ← 用户-助手对话轮次
│               ├── ThinkingMessage
│               ├── ToolMessage / ToolGroupMessage / ToolSummaryMessage
│               ├── SkillMessage
│               └── MarkdownText (助手回复)
└── ShellFooter                   ← 底部
    ├── statusLine                ← 状态文字
    ├── pendingSkill 提示
    ├── TextInput                 ← 用户输入框
    ├── SlashMenu                 ← 斜杠命令面板
    └── StatusHud                 ← 状态栏 (model/git/session/tokens/tools)
```

### 数据流

```
用户输入
  ↓
useShellInput (键盘事件路由)
  ↓
submitChat / submitSetup / runShellCommand
  ↓
NodeBridge.sendMessage(text, skillName?)
  ↓
api.streamMessage() → SSE stream
  ↓
store.applyEvent(event) → 更新 transcript/toolActivity/tokenUsage
  ↓
React 重渲染 → Transcript / StatusHud
```

---

## 入口与启动流程 (`index.tsx`)

### 模块级初始化

文件顶层创建全局单例——这在整个 Shell 生命周期内只发生一次：

```typescript
const store = createAppStore();       // Zustand store 单例
const bridge = new NodeBridge(store);  // 后端桥接单例
const getState = store.getState;       // 便捷引用
```

### 颜色常量

Shell 使用统一的颜色主题：

| 常量 | 色值 | 用途 |
|------|------|------|
| `ACCENT` | `#ff4d94` | 品牌色/高亮（粉红） |
| `MUTED` | `#8b8b91` | 次要文字 |
| `BORDER` | `#5c5c63` | 边框/分隔线 |
| `WARNING` | `#ffd166` | 警告状态 |
| `INFO` | `#e9e9ea` | 普通信息文字 |

### `SmithApp` 组件

顶层 React 组件，唯一被 `render()` 挂载的组件。

**初始化流程：**

1. `useEffect` 中调用 `bridge.boot()` 启动后端连接
2. 订阅 store 中所有状态字段
3. 计算 `slashItems`（由 `skills` + `plugins` + `inputValue` 派生）
4. 注册 `useShellInput` 处理键盘事件

**布局结构（垂直排列）：**

```
Box (flexDirection="column", paddingY=1)
├── Box (头部区域): "Agent-Smith v0.2.1"
├── Box (内容区域): <ShellContent />
└── Box (底部区域): <ShellFooter />
```

### `HeroPanel` 组件

显示 ASCII art logo 和 ghost buddy 图案，加一行操作提示：

```
███████╗███╗   ███╗██╗████████╗██╗  ██╗     ─╥╥─
██╔════╝████╗ ████║██║╚══██╔══╝██║  ██║   ▄██████▄
███████╗██╔████╔██║██║   ██║   ███████║   ██ ██ ██
╚════██║██║╚██╔╝██║██║   ██║   ██╔══██║    ██████
███████╗██║ ╚═╝ ██║██║   ██║   ██║  ██║   ╰╯╰╮╭╯╰╯

Type `/` for commands · `/help` for all
```

### `SetupPanel` 组件

初始配置向导面板，当 `mode === "setup"` 时显示。使用 `SETUP_FIELDS`（`provider` / `base_url` / `model` / `api_key` / `save`）逐字段引导用户填写 LLM 配置。API key 字段以 `"•"` 掩码显示。

### `SessionsPanel` / `PluginsPanel` / `SkillsPanel`

侧面板组件，分别由 `/sessions`、`/plugins`、`/skills` 命令触发。各自展示最多 8-12 条记录。

### `SlashMenu` 组件

输入以 `/` 开头时弹出的命令面板。支持分类展示（Commands / Skills / Plugins）、过滤搜索、上下键导航选中。

### 消息提交流程 `submitChat()`

```typescript
async function submitChat(
  value: string,
  busy: boolean,
  pendingSkill: SkillSummary | null,
  skills: SkillSummary[],
  slashMenuOpen: boolean,
  slashItems: SlashItem[],
  slashIndex: number,
  exit: () => void,
): Promise<void>
```

执行步骤：

1. 空输入或 busy 状态时直接返回
2. 将输入推入 `inputHistory`，清空输入框
3. 尝试通过 `parseSkill()` 解析 `/skill <name> [prompt]` 语法
4. 如果输入以 `/` 开头且不是技能调用：
   - 先尝试 slash menu 补全
   - 否则执行 `runShellCommand()`
5. 最终调用 `bridge.sendMessage(prompt, skillName)`

### 配置提交流程 `submitSetup()`

在 setup 模式下处理表单提交。逐字段前进（Tab / Enter），到 `save` 字段时校验必填项（`base_url`、`model`、`api_key`），然后调用 `bridge.saveConfig()`。

---

## 后端桥接 (`bridge.ts`)

`NodeBridge` 是 Shell 与后端通信的唯一通道。**UI 组件从不直接调用 `api.ts`**——所有后端交互都经由 bridge。

### 类定义

```typescript
export class NodeBridge {
  private activeRequest: AbortController | null = null;
  constructor(private store: StoreApi<AppStore>) {}
}
```

### `boot()` 启动流程

```
boot()
  ├── ensureLocalServer()          ← 探测或启动后端
  ├── getLlmConfig()               ← 读取 LLM 配置
  ├── 如果未配置 → 进入 setup 模式
  └── hydrateShell()               ← 加载全部元数据
```

详细步骤：

1. 调用 `ensureLocalServer()` 获取可用的后端 URL
2. 获取 LLM 配置（`GET /api/config/llm`）
3. 如果 `config.configured === false`，切换到 `mode: "setup"`，预填 openai 默认值
4. 否则调用 `hydrateShell()` 完成初始化

### `hydrateShell(baseUrl, bootNotes?)` 元数据加载

并行加载三类元数据：

```typescript
const [sessions, plugins, skills] = await Promise.all([
  listSessions(baseUrl),
  listPlugins(baseUrl),
  listSkills(baseUrl),
]);
```

然后调用 `store.hydrate()` 一次性更新状态，进入 `mode: "chat"`。sessions 和 skills 的加载失败会降级为警告而非崩溃。

### `sendMessage(text, skillName?)` 消息发送

完整流程：

1. **就绪检查** `getReadySession()`：确认 `baseUrl` 和 `agent` 存在
2. **创建请求** `startRequest()`：新建 `AbortController`，设置 `busy: true`
3. **会话管理** `getOrCreateSession()`：无会话时自动创建，标题取用户输入前 40 字符
4. **推入对话** `store.pushTurn(text)`
5. **流式响应** `streamResponse()`：遍历 SSE 事件，逐个调用 `store.applyEvent()`
6. **关闭轮次** `store.closeTurn()`
7. **刷新会话列表** `refreshSessions()`

终端状态处理：

| `StreamTerminalStatus` | 行为 |
|------------------------|------|
| `"completed"` | 显示 "Ready. Type the next task or /help." |
| `"incomplete"` | 推送警告 "Model output limit reached" |
| `"failed"` | 推送错误 "Agent execution failed" |

### `cancelRequest()` 请求取消

中止 `activeRequest`（`AbortController.abort()`），关闭当前轮次，设置 `busy: false`。

### `resumeSession(session)` 会话恢复

1. 调用 `listMessages()` 获取历史消息
2. 通过 `restoreTranscript()` 将 `Message[]` 重建为 `TranscriptEntry[]`（按 user-assistant 配对）
3. 更新 store 中的 `currentSession` / `transcript` / `turnCount`

### 其他方法

| 方法 | 说明 |
|------|------|
| `saveConfig(input)` | POST 保存 LLM 配置后重新 hydrate |
| `refreshPlugins()` | 重新获取插件列表 |
| `refreshSkills()` | 重新获取技能列表 |
| `togglePlugin(name, enable)` | 启用/禁用插件后刷新列表 |

---

## API 客户端 (`api.ts`)

纯函数式 HTTP 客户端，不持有任何状态。使用 `fetch()` API。

### 类型定义

```typescript
export type LlmConfig = {
  configured: boolean;
  has_api_key: boolean;
  provider: string;
  model: string;
  base_url: string;
};

export type AgentProfile = {
  id: string;
  name: string;
  role: string;
  description?: string;
};

export type Session = {
  id: string;
  agent_id: string;
  title: string;
  created_at: string;
  last_message_preview?: string | null;
  last_message_at?: string | null;
  message_count: number;
};

export type PluginManifest = {
  name: string;
  enabled?: boolean;
  installed?: boolean;
  status?: string;
  version?: string;
  description?: string;
  trigger_type?: string;
  skill_count?: number;
  skills?: Array<{ path?: string }>;
};

export type SkillSummary = {
  name: string;
  description: string;
  source: string;
  version: string;
  argument_hint: string;
};

export type TokenUsage = {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
};

export type Message = {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type LlmConfigInput = {
  provider: string;
  api_key?: string;
  base_url: string;
  model: string;
};
```

### REST API 函数

| 函数 | 方法 | 路径 | 说明 |
|------|------|------|------|
| `getLlmConfig(baseUrl)` | GET | `/api/config/llm` | 获取 LLM 配置 |
| `setLlmConfig(baseUrl, payload)` | POST | `/api/config/llm` | 设置 LLM 配置 |
| `getAgentProfile(baseUrl)` | GET | `/api/agent` | 获取 Agent 档案 |
| `ensureAgentProfile(baseUrl)` | POST | `/api/agent/ensure` | 确保 Agent 存在 |
| `listSessions(baseUrl)` | GET | `/api/agent/sessions` | 会话列表 |
| `createSession(baseUrl, title)` | POST | `/api/agent/sessions` | 创建会话 |
| `listMessages(baseUrl, sessionId)` | GET | `/api/agent/sessions/{id}/messages` | 消息列表 |
| `listPlugins(baseUrl)` | GET | `/api/plugins` | 插件列表（失败返回 `[]`） |
| `enablePlugin(baseUrl, name)` | POST | `/api/plugins/{name}/enable` | 启用插件 |
| `disablePlugin(baseUrl, name)` | POST | `/api/plugins/{name}/disable` | 禁用插件 |
| `listSkills(baseUrl)` | GET | `/api/agent/skills` | 技能列表 |

### SSE 流式消息

#### `StreamEvent` 联合类型

```typescript
export type StreamEvent =
  | { type: "message"; text: string }
  | { type: "thinking"; text: string; done: boolean }
  | { type: "tool_call"; id: string; name: string; hint: string }
  | { type: "tool_result"; id: string; error: boolean; blocked: boolean; preflight: boolean; summary: string }
  | { type: "skill"; name: string; status: string }
  | ({ type: "token_usage" } & TokenUsage)
  | { type: "done"; id?: string; status: StreamTerminalStatus };

export type StreamTerminalStatus = "completed" | "failed" | "incomplete";
```

#### `streamMessage()` 流式接口

```typescript
export async function* streamMessage(
  baseUrl: string,
  sessionId: string,
  content: string,
  options?: { context?: string; skillName?: string; signal?: AbortSignal },
): AsyncGenerator<StreamEvent, void, void>
```

发送 POST 到 `/api/agent/sessions/{sessionId}/messages/stream`，`Accept: text/event-stream`。

#### SSE 解析管线

```
HTTP Response body (ReadableStream<Uint8Array>)
  ↓ TextDecoder
  ↓ splitSseBuffer() — 按 "\n\n" 分割 SSE 帧
  ↓ parseSseChunk() — 解析 event: / data: 行
  ↓ SSE_EVENT_DECODERS[eventName]() — 类型安全地转为 StreamEvent
  ↓ yield 给调用者
```

支持的 SSE 事件名及其映射：

| SSE event | 对应 StreamEvent.type | 说明 |
|-----------|----------------------|------|
| `message` | `"message"` | 助手文本增量 |
| `thinking` | `"thinking"` | 思考过程 |
| `tool_call` | `"tool_call"` | 工具调用开始 |
| `tool_result` | `"tool_result"` | 工具调用结果 |
| `skill` | `"skill"` | 技能状态变更 |
| `token_usage` | `"token_usage"` | Token 用量统计 |
| `done` | `"done"` | 流结束信号 |
| `error` | 抛出异常 | 服务端错误 |

如果流结束时未收到 `done` 事件，抛出 `"SSE stream ended before a done event was received."`。

---

## 状态管理 (`store.ts`)

使用 Zustand vanilla store（`createStore`，非 React 绑定），在 `index.tsx` 中通过 `useStore(store, selector)` 连接 React。

### 模式与面板

```typescript
export type Mode = "boot" | "setup" | "chat";
export type Panel = "welcome" | "chat" | "sessions" | "plugins" | "skills";
```

| Mode | 说明 |
|------|------|
| `"boot"` | 启动中，显示 Spinner |
| `"setup"` | 初始配置向导 |
| `"chat"` | 正常聊天模式 |

| Panel | 说明 |
|-------|------|
| `"welcome"` | 欢迎页，显示 HeroPanel |
| `"chat"` | 聊天区域，显示 Transcript |
| `"sessions"` | 会话列表 |
| `"plugins"` | 插件列表 |
| `"skills"` | 技能列表 |

### `AppState` 完整字段

| 字段 | 类型 | 初始值 | 说明 |
|------|------|--------|------|
| `mode` | `Mode` | `"boot"` | 应用模式 |
| `panel` | `Panel` | `"welcome"` | 当前面板 |
| `baseUrl` | `string` | `""` | 后端 URL |
| `config` | `LlmConfig \| null` | `null` | LLM 配置 |
| `agent` | `AgentProfile \| null` | `null` | Agent 档案 |
| `sessions` | `Session[]` | `[]` | 会话列表 |
| `plugins` | `PluginManifest[]` | `[]` | 插件列表 |
| `skills` | `SkillSummary[]` | `[]` | 技能列表 |
| `currentSession` | `Session \| null` | `null` | 当前活跃会话 |
| `transcript` | `TranscriptEntry[]` | `[]` | 对话记录 |
| `turnCount` | `number` | `0` | 对话轮次计数 |
| `toolActivity` | `ToolActivity` | `createToolActivity()` | 工具活动统计 |
| `tokenUsage` | `TokenUsage` | `{0,0,0}` | Token 累计用量 |
| `viewMode` | `TranscriptViewMode` | `"compact"` | 视图模式 |
| `pendingSkill` | `SkillSummary \| null` | `null` | 已装填待发送的技能 |
| `busy` | `boolean` | `false` | 请求进行中 |
| `inputValue` | `string` | `""` | 输入框当前值 |
| `inputHistory` | `string[]` | `[]` | 输入历史 |
| `historyIndex` | `number` | `-1` | 历史导航位置（-1 = 无） |
| `statusLine` | `string` | `"Booting Smith..."` | 底部状态文字 |
| `setupDraft` | `SetupDraft` | openai 预设 | 配置草稿 |
| `setupIndex` | `number` | `0` | 配置向导当前字段 |
| `slashIndex` | `number` | `0` | 斜杠菜单选中项 |
| `welcomeNotice` | `{text, tone} \| null` | `null` | 欢迎页通知 |

`SetupDraft` 默认值：`{ provider: "openai", base_url: "https://api.openai.com/v1", model: "gpt-4.1-mini", api_key: "" }`。

### `AppActions` 方法

| 方法 | 签名 | 说明 |
|------|------|------|
| `set` | `(partial: Partial<AppState>) => void` | 通用状态更新 |
| `pushSystemLine` | `(text: string, tone?: "info" \| "error") => void` | 追加系统消息到 transcript |
| `pushHistory` | `(text: string) => void` | 追加到输入历史，重置 historyIndex |
| `pushTurn` | `(userText: string) => void` | 追加新对话轮次，turnCount + 1 |
| `applyEvent` | `(event: StreamEvent) => void` | 应用 SSE 事件到 transcript 和 toolActivity |
| `closeTurn` | `() => void` | 关闭最近一轮（标记 `streaming: false`） |
| `resetChat` | `() => void` | 重置为空白会话（panel = "welcome"） |
| `clearChat` | `() => void` | 清空对话但保持 chat 面板 |
| `hydrate` | `(opts: HydrateOptions) => void` | 从后端数据初始化状态 |

`applyEvent` 的路由逻辑：

- `token_usage` 事件 → 累加 `tokenUsage`，更新 `toolActivity`
- 其他事件 → 更新 `transcript`（通过 `applyStreamEvent`）和 `toolActivity`

`hydrate` 会保留已有的 `transcript` 和 `currentSession`（支持 mid-session 配置保存后不丢失进行中会话）。

---

## HUD 组件 (`hud.tsx`)

`StatusHud` 是底部状态栏组件，用 `memo()` 包裹以避免不必要的重渲染。

### 显示信息

状态栏分两行：**头部行** 和 **活动行**。

**头部行包含的片段：**

| 片段 | 颜色 | 示例 |
|------|------|------|
| 模型名 | `#e5c07b` (MODEL) | `[gpt-4.1-mini]` |
| 项目名 | `#98c379` (PROJECT) | `Agent-Smith` |
| Git 分支 | `#c678dd` (GIT) | `git main` |
| 会话 ID | `#61afef` (SESSION) | `session a1b2c3` |
| 对话轮次 | `#8b8b91` (MUTED) | `3 turns` |
| 视图模式 | `#8b8b91` (MUTED) | `compact` |
| Token 用量 | `#ffd166` (WARNING) | `tok 12.5k` |

片段间以 ` | ` 分隔。Token 用量格式化规则：>= 1M 显示 `Xm`，>= 1K 显示 `Xk`，否则显示原始数字。

**活动行展示工具调用状态：**

| 标记 | 含义 | 颜色 |
|------|------|------|
| `◐` | 正在运行的工具 | WARNING |
| `✓` | 成功完成的工具 | SUCCESS (`#93f77b`) |
| `⛔` | 被权限阻止的工具 | WARNING |
| `◆` | 事实预检的工具 | WARNING |
| `!` | 出错的工具 | ERROR (`#e06c75`) |

### 自适应布局

HUD 使用 `useWindowSize()` 获取终端列宽，自动换行和截断：

- `wrapParts()` 将片段按终端宽度分行
- `truncatePart()` 在宽度不足时截断并添加 `"..."` 后缀
- `textWidth()` 支持 CJK 全角字符和 emoji 的正确宽度计算（通过 `Intl.Segmenter` 和 Unicode 码位范围判断）

### Git 分支读取

`useGitBranch(cwd)` hook 通过 `execFile("git", ...)` 异步读取当前分支名，每 5 秒刷新。支持 detached HEAD 显示为 `detached@<short-hash>`。

---

## 对话渲染 (`transcript.tsx`)

### 数据模型

#### `TranscriptEntry` 联合类型

```typescript
export type TranscriptEntry = SystemEntry | TurnEntry;
```

**`SystemEntry`** — 系统消息

```typescript
export type SystemEntry = {
  id: string;
  kind: "system";
  text: string;
  tone: "info" | "error";
};
```

**`TurnEntry`** — 一轮用户-助手对话

```typescript
export type TurnEntry = {
  id: string;
  kind: "turn";
  userText: string;
  assistantText: string;
  blocks: TurnBlock[];
  streaming: boolean;
};
```

#### `TurnBlock` 联合类型

```typescript
export type TurnBlock = ThinkingBlock | ToolBlock | SkillBlock;
```

| Block 类型 | 字段 | 说明 |
|------------|------|------|
| `ThinkingBlock` | `text`, `done` | 模型思考过程 |
| `ToolBlock` | `toolCallId`, `name`, `hint`, `state`, `summary` | 工具调用记录 |
| `SkillBlock` | `name`, `state` | 技能执行记录 |

`ToolBlock.state` 的值：`"running"` / `"success"` / `"error"` / `"blocked"` / `"preflight"`。

`SkillBlock.state` 的值：`"running"` / `"done"` / `"error"`。

### 视图模式

```typescript
export type TranscriptViewMode = "compact" | "transcript";
```

| 模式 | 特征 |
|------|------|
| `compact` | 折叠已完成工具为摘要行，最多显示 16 条记录 |
| `transcript` | 展开所有工具细节，最多显示 24 条记录 |

### `applyStreamEvent()` 事件映射

将 `StreamEvent` 转化为 `TranscriptEntry[]` 更新。核心机制：通过 `updateLastTurn()` 不可变地修改最后一个 `TurnEntry`。

| 事件类型 | 行为 |
|----------|------|
| `message` | 追加文本到 `assistantText`，完成进行中的 thinking block |
| `thinking` | 追加或更新 thinking block（空文本 + done 时删除） |
| `tool_call` | 新增或更新 tool block（设为 running） |
| `tool_result` | 更新对应 tool block 的 state 和 summary |
| `skill` | start 时新增，其他状态更新最近匹配的 skill block |
| `token_usage` | 不修改 entries（由 store 单独处理） |
| `done` | 调用 `closeLatestTurn()` |

### compact 模式的折叠逻辑

1. **工具分组** `groupToolBlocks()`：连续同名工具合并为 `ToolGroupBlock`
2. **成功折叠** `collapseCompletedTools()`：将所有已成功的工具 block 合并为一个 `ToolSummaryBlock`（形如 `✓ 3x read_file  2x search`），只在折叠了 >= 2 个 block 时生效

### 渲染组件

| 组件 | 说明 |
|------|------|
| `Transcript` | 容器组件，渲染 entries 列表，turnEntry 之间加分隔线 |
| `SystemMessage` | 系统消息，使用 `MarkdownText` 渲染 |
| `TurnViewWithMode` | 对话轮次渲染，包含用户输入 + blocks + 助手回复 |
| `ThinkingMessage` | 斜体灰色思考过程，compact 模式截断为 2 行 |
| `ToolMessage` | 工具调用详情，含 marker + name + hint + summary |
| `ToolGroupMessage` | 分组工具，显示 "3x tool_name" 和状态统计 |
| `ToolSummaryMessage` | 折叠后的成功工具汇总行 |
| `SkillMessage` | 技能执行状态，紫色标记 |

助手回复使用 `@assistant-ui/react-ink-markdown` 的 `MarkdownText` 组件渲染，支持终端中的 Markdown 格式。文本经 `stripEmojiIcons()` 处理，移除装饰性 emoji。

流式进行中（`streaming && !hasAssistantBody`）时显示 Spinner + "Processing..."。

---

## 命令系统 (`commands.ts`)

### `SlashItem` 类型

```typescript
export type SlashItem = {
  id: string;
  kind: "command" | "skill";
  title: string;
  command: string;
  description: string;
  category: string;
  skill?: SkillSummary;
};
```

### 内置命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示命令帮助 |
| `/exit` | 退出 Shell |
| `/new` | 创建新会话，保留当前会话记录 |
| `/config` | 打开 LLM 配置编辑 |
| `/sessions` | 切换到会话列表面板 |
| `/skills` | 切换到技能列表面板 |
| `/plugins` | 切换到插件列表面板 |
| `/clear` | 删除当前会话及消息，再创建新会话 |
| `/compact` | 切换到紧凑视图 |
| `/plugin <enable\|disable> <name>` | 启用/禁用插件 |
| `/resume <id>` | 恢复指定会话 |

### `buildSlashItems()` 面板构建

将内置命令、技能列表、插件列表合并为统一的 `SlashItem[]`：

- **Commands** 分类：10 个固定命令
- **Skills** 分类：从 `skills[]` 动态生成，`kind: "skill"`
- **Plugins** 分类：从 `plugins[]` 动态生成，根据 `enabled` 状态生成 enable/disable 命令

### `filterSlash()` 搜索过滤

```typescript
export function filterSlash(items: SlashItem[], input: string): SlashItem[]
```

输入以 `/` 开头时触发。空查询返回前 12 项；有查询时在 `command + title + description` 中做大小写不敏感子串匹配，最多返回 12 条。

### `parseSkill()` 技能语法解析

```typescript
export function parseSkill(raw: string, skills: SkillSummary[]): { skill: SkillSummary; prompt: string } | null
```

解析 `/skill <name> [prompt]` 格式。如果匹配技能名但没有 prompt，返回 `{ skill, prompt: "" }`（此时 `submitChat` 会进入 "arm skill" 状态）。

### `runShellCommand()` 命令执行

```typescript
export async function runShellCommand(raw: string, context: CommandContext): Promise<void>
```

先在 `COMMAND_HANDLERS` 中查找；找不到时尝试匹配技能名。匹配到技能且有参数时直接发送消息；无参数时装填技能（arm）。

---

## 输入处理 (`input.ts`)

### `useShellInput` Hook

```typescript
export function useShellInput(options: ShellInputOptions): void
```

使用 Ink 的 `useInput` hook 注册全局键盘监听。所有按键事件通过 `routeInput()` 分发。

### 按键路由优先级

`routeInput()` 按以下顺序检查并短路：

1. **Ctrl+C** → 取消正在执行的请求（busy 时），或退出 Shell
2. **Setup 模式** → 转到 `handleSetupInput()`
3. **Ctrl+O** → 切换 compact/transcript 视图（抑制字符输入）
4. **Slash 菜单导航** → Tab 补全 / 上下键选择
5. **Escape** → 取消请求 / 关闭 slash 菜单 / 清除 pendingSkill
6. **历史导航** → 上下键浏览输入历史
7. **Tab 面板切换** → 在 welcome → sessions → skills → plugins → chat 间循环

### 详细按键行为

| 按键 | 上下文 | 行为 |
|------|--------|------|
| `Ctrl+C` | busy | 取消当前请求 |
| `Ctrl+C` | idle | 退出 Shell |
| `Ctrl+O` | chat | 切换 compact / transcript 视图 |
| `Tab` | setup | 移到下一字段 |
| `Up/Down` | setup | 上下切换字段 |
| `Escape` | setup, 已配置 | 返回 chat 模式 |
| `Tab` | slash menu open | 将选中命令填入输入框 |
| `Up/Down` | slash menu open | 导航 slash 菜单 |
| `Escape` | slash menu open | 关闭菜单，清空输入 |
| `Escape` | pendingSkill | 清除装填的技能 |
| `Escape` | busy | 取消请求 |
| `Up/Down` | 普通输入 | 浏览输入历史 |
| `Tab` | 普通输入 | 循环切换面板 |
| `Enter` | 输入框 | 提交消息（chat）或保存字段（setup） |

### 输入抑制机制

`suppressRef` 用于处理 `Ctrl+O` 等快捷键——防止控制字符被追加到输入框。当 `suppressRef.current` 非 null 时，`handleInputChange` 会检查新值是否只是在原值后面多了被抑制的字符，如果是则忽略。

---

## 活动追踪 (`activity.ts`)

跟踪当前会话中所有工具调用的状态统计。

### `ToolActivity` 类型

```typescript
export type ToolActivity = {
  calls: Record<string, ToolCall>;     // toolCallId → 调用记录
  running: Record<string, string>;     // toolCallId → 工具名（正在运行的）
  successes: Record<string, number>;   // 工具名 → 成功计数
  errors: Record<string, number>;      // 工具名 → 错误计数
  blocked: Record<string, number>;     // 工具名 → 阻止计数
  preflight: Record<string, number>;   // 工具名 → 预检计数
};

export type ToolState = "running" | "success" | "error" | "blocked" | "preflight";
```

### `applyToolActivity()` 事件处理

```typescript
export function applyToolActivity(activity: ToolActivity, event: StreamEvent): ToolActivity
```

只处理两种事件：

- `tool_call` → `startTool()`：注册为 running 状态
- `tool_result` → `settleTool()`：根据 `toolStateFromResult()` 判断最终状态，从 running 移出，计入对应计数器

`toolStateFromResult()` 优先级：`preflight` > `blocked` > `error` > `success`。

所有更新都是不可变的（返回新对象），适配 Zustand 的浅比较。

---

## 输出处理 (`output.ts`)

单一职责：移除助手文本中的装饰性 emoji。

```typescript
export function stripEmojiIcons(text: string): string
```

使用两个正则表达式：

- `EMOJI_ICON` — 匹配 emoji 图标及其后的可选空白（支持组合 emoji、ZWJ 序列、区域指示符、键帽序列）
- `EMOJI_ARTIFACT` — 清理残留的变体选择器（`︎` / `️`）、ZWJ（`‍`）和组合封闭圆（`⃣`）

---

## 配置向导 (`setup.ts`)

首次启动或 `/config` 命令时使用的配置表单逻辑。

### Provider 预设

```typescript
export const PROVIDER_PRESETS = {
  openai: { base_url: "https://api.openai.com/v1", model: "gpt-4.1-mini" },
  anthropic: { base_url: "https://api.anthropic.com", model: "claude-sonnet-4-20250514" },
};
```

选择 provider 时自动填充 `base_url` 和 `model`。目前仅支持 `openai` 和 `anthropic` 两个预设。

### 表单字段

```typescript
export const SETUP_FIELDS = ["provider", "base_url", "model", "api_key", "save"] as const;
```

字段导航支持 Tab/上下键，wrap 与 clamp 两种模式（键盘导航时 wrap，Enter 提交时 clamp）。

### 关键函数

| 函数 | 说明 |
|------|------|
| `createSetupDraft(config)` | 从现有配置创建草稿，api_key 始终清空 |
| `setProvider(draft, value)` | 设置 provider 并自动填充预设，非法值返回 null |
| `setSetupField(draft, field, value)` | 更新指定字段 |
| `setupFieldAt(index)` | 索引转字段名 |
| `nextSetupIndex(index, direction, wrap)` | 计算下一字段索引 |

---

## 会话重置 (`conversation.ts`)

提供 `createEmptyConversation()` 工厂函数，用于 `/new`（`resetChat`）和 `/clear`（`clearChat`）。

```typescript
export function createEmptyConversation(panel: ConversationPanel, statusLine: string): EmptyConversation
```

返回的对象包含清零的 `transcript`、`turnCount`、`toolActivity`、`tokenUsage`、`pendingSkill`、`welcomeNotice`，以及指定的 `panel` 和 `statusLine`。区别在于：

- `resetChat` → `panel: "welcome"`，回到欢迎页
- `clearChat` → `panel: "chat"`，保持聊天面板

---

## 开发服务器 (`dev-server.ts`)

自动探测或启动本地 Python 后端的管理器。

### 连接策略

```typescript
export async function ensureLocalServer(): Promise<ServerConnection>
```

**完整流程：**

```
ensureLocalServer()
  ├── serverTarget()              ← 确定目标 URL
  │   └── 读取 SMITH_SERVER_URL 环境变量
  │       默认 http://127.0.0.1:8140
  │
  ├── inspectExistingServer()     ← 探测已有服务
  │   ├── isHealthy() → GET /api/health
  │   └── compatibilityIssue() → GET /openapi.json
  │       检查 REQUIRED_PATHS 是否全部存在
  │
  ├── [已有兼容服务] → 直接返回 {started: false}
  ├── [SMITH_SERVER_URL 设了但服务不对] → 抛异常
  │
  ├── launchUrl()                 ← 确定启动端口
  │   ├── 已有服务占用端口 → findAvailablePort(8141..8160)
  │   └── 端口空闲 → 使用 8140
  │
  ├── launchLocalServer()         ← 启动 Python 进程
  │   └── spawn("uv", ["run", "uvicorn", "app.main:app", "--port", port])
  │       cwd = <repo-root>/server
  │
  └── waitForCompatibleServer()   ← 等待健康检查通过
      └── 最多轮询 40 次，每次间隔 500ms（总计 20 秒）
```

### 端口管理

| 场景 | 行为 |
|------|------|
| 8140 空闲 | 直接使用 |
| 8140 被占用但不是 Smith | 从 8141 开始搜索空闲端口 |
| 8140 被老版 Smith 占用 | 启动新实例在新端口，附带提示信息 |
| 8140-8160 全部被占用 | 抛异常 |

### 兼容性检查

`compatibilityIssue()` 会检查 `/openapi.json` 中是否包含以下必需路由：

```typescript
const REQUIRED_PATHS = [
  "/api/config/llm",
  "/api/agent",
  "/api/agent/ensure",
  "/api/plugins",
  "/api/agent/skills",
  "/api/agent/sessions/{session_id}/messages/stream",
];
```

### 进程生命周期

- Shell 拥有它启动的后端进程（`ownedServer` 模块变量）
- 注册 `process.once("exit" | "SIGINT" | "SIGTERM")` 清理钩子
- 清理时发送 `SIGTERM` 给后端进程
- `SIGINT` 退出码 130，`SIGTERM` 退出码 143

### `resolveRepoRoot()`

```typescript
export function resolveRepoRoot(): string
```

从当前文件（`dist/` 下的编译产物）向上两级确定仓库根目录，用于定位 `server/` 目录。

---

## 构建与运行

### 构建流程

```bash
cd shell
npm install        # 安装依赖
npm run build      # TypeScript 编译到 dist/
```

输出结构：

```
shell/
├── bin/
│   └── smith.js          ← CLI 入口（2 行 shim）
├── src/                  ← TypeScript 源码
├── dist/                 ← 编译产物（tsc 输出）
│   └── index.js          ← 主入口
└── package.json          ← bin.smith → ./bin/smith.js
```

`bin/smith.js` 内容：

```javascript
#!/usr/bin/env node
import "../dist/index.js";
```

### `smith` CLI 入口

`package.json` 中声明了 `bin.smith`，通过 `npm link` 或全局安装后，用户在终端直接运行 `smith` 即可启动 Shell。

启动后的完整路径：

```
smith (CLI)
  → bin/smith.js
    → dist/index.js
      → render(<SmithApp />)
        → bridge.boot()
          → ensureLocalServer()
            → 探测/启动 Python 后端
          → getLlmConfig()
          → hydrateShell()
        → 进入交互循环
```

### 环境变量

| 变量 | 说明 |
|------|------|
| `SMITH_SERVER_URL` | 覆盖默认后端地址（`http://127.0.0.1:8140`） |

### 测试

```bash
cd shell
npm test           # tsc 类型检查 + 运行测试
```

测试文件位于 `src/` 下，与源文件同目录：`activity.test.ts`、`api.test.ts`、`output.test.ts`。使用 `node:test` 内置测试运行器。
