# OpenHanako (HanaAgent) 调研与借鉴

## 1. 项目概况

**仓库**: [github.com/liliMozi/openhanako](https://github.com/liliMozi/openhanako)
**版本**: v0.350.2 (Apache-2.0)
**定位**: "有记忆、有灵魂的私人 AI 助理" —— 面向普通桌面用户的图形化 AI Agent，强调人格陪伴和多平台触达。

### 技术栈

| 层级 | 技术 |
|---|---|
| 桌面端 | Electron 42 |
| 前端 | React 19 + Zustand 5 + CSS Modules |
| 构建 | Vite 7 |
| 本地服务 | Hono + @hono/node-server (HTTP + WebSocket) |
| Agent 运行时 | Pi SDK (`@mariozechner/pi-ai`) |
| 数据库 | better-sqlite3 (WAL 模式) |
| 终端 | node-pty |
| 测试 | Vitest |
| Node 要求 | >= 24.12.0 < 25 |
| 平台 | macOS (签名公证) / Windows / Linux / 移动端 PWA |

### 源码结构

```
core/           引擎编排层 (HanaEngine Facade + Manager 群)
lib/            核心库 (记忆、工具、沙盒、Bridge 适配器)
server/         Hono HTTP + WebSocket 服务 (独立 Node 进程)
hub/            调度器、频道路由、事件总线
desktop/        Electron 应用 + React 前端
shared/         跨层共享 (config schema, error bus, 模型引用)
plugins/        内置系统插件 (随应用打包)
skills2set/     内置技能定义
```

核心类 `HanaEngine` (`core/engine.ts`, 2655 行) 是一个 **Thin Facade**，持有全部 Manager（AgentManager / SessionCoordinator / ConfigCoordinator / ChannelManager / BridgeSessionManager / ModelManager / SkillManager / PluginManager 等），对外暴露统一 API。

---

## 2. 架构对比

### 相同点

两者都是 **桌面优先** 的本地 AI 代理产品：
- 都以桌面 App 为产品入口，本地 Server 作为后端
- 都用 SQLite (WAL 模式) 做本地持久化
- 都有记忆系统、技能系统、工具系统
- 都支持多 Agent 协作

### 核心差异

| 维度 | Agent-Smith | OpenHanako |
|---|---|---|
| **前端技术** | 原生 SwiftUI (macOS only) | Electron 42 (跨平台) |
| **后端语言** | Python (FastAPI + uv) | TypeScript (Hono + Node) |
| **分层** | 五层单向依赖 (common→engine→agents→server→macos-app) | Facade + Manager 群 (core/lib/hub/server/desktop) |
| **执行模型** | 混合 DAG + ReAct 四层嵌套 (SkillChain → 门禁 → ReAct → 工具) | 单层 ReAct (Pi SDK agent loop) |
| **质量保证** | 12 个门禁 (PlanningGate, DesignGate, TestGate 等) | LLM 自判断 |
| **定位** | 企业级数字员工 | 个人陪伴助理 |
| **Agent 模板** | .md/.yaml/.json 文件 (无代码定义) | JSON + identity.md + ishiki.md (意识文件) |
| **System Prompt** | 11 层组装 (assembler.py) | 静态前缀 + 动态尾部 (prefix cache 优化) |
| **IM 触达** | 无 (仅 macOS App) | 5 平台桥接 (Telegram/飞书/钉钉/QQ/微信) |
| **插件系统** | 单级 (polling/webhook/manual) | 二级权限 (restricted/full-access) + 10 种贡献类型 |

### 架构图对比

**Agent-Smith 五层架构**:
```
macos-app/ ──HTTP/SSE──→ server/ ──import──→ engine/ ──import──→ common/
                            │                    ↑
                            └── 读取 ──→ agents/  ┘
```

**OpenHanako 架构**:
```
desktop/ ──IPC──→ server/ ──callback──→ core/ (HanaEngine Facade)
                                         ├── hub/ (EventBus + 路由)
                                         ├── lib/ (记忆/工具/Bridge)
                                         └── plugins/ (内置 + 社区)
```

---

## 3. 五个可借鉴的设计

### 3a. 记忆编译管线 + 指纹缓存

#### 他们怎么做的

**源文件**: `lib/memory/compile.ts` (624 行)

OpenHanako 实现了一套 **v3 四块独立编译 + assemble** 的记忆蒸馏系统：

| 编译函数 | 输出文件 | 时间窗口 | 职责 |
|---|---|---|---|
| `compileToday()` | `today.md` | 当天 sessions | 3-5 条粗颗粒事件摘要 (max 300 字) |
| `compileWeek()` | `week.md` | 过去 7 天滑动窗口 | 3-5 条本周主题概要 (max 400 字) |
| `compileLongterm()` | `longterm.md` | 历史累积 | 将 week.md fold 进长期记忆 (每日一次) |
| `compileFacts()` | `facts.md` | 最近 30 天 | 提取重要事实，继承上一版 facts |

`assemble()` 同步读取四个文件，拼成最终的 `memory.md`，注入到 system prompt。四个标题始终保留，空栏写占位符防格式漂移。

**关键机制 —— 指纹缓存**：每个编译函数都有独立的 MD5 指纹文件 (`outputPath + ".fingerprint"`)：

```typescript
// lib/memory/compile.ts
const fpKeys = sessions.map((s) => `${s.session_id}:${s.updated_at}`);
const fp = computeFingerprint(fpKeys);  // crypto.createHash("md5")
// 命中指纹 -> 跳过编译 (return "skipped")
```

设计细节：**空 sessions 不写 fingerprint**。如果写了 "empty" 指纹，rollingSummary 失败恢复后该指纹仍会命中，导致 today.md 永远卡在 0 bytes。

所有编译通过 `_compactLLM()` 统一调用 (utility_large 模型, temperature=0.3, timeout 60s)，Prompt 严格约束只记录用户画像（谁、喜好、关注），不记录执行细节/文件名/工具/命令。

#### Agent-Smith 目前的做法

**源文件**: `engine/memory/dream.py` (241 行)

`DreamConsolidator` 使用预览/应用两阶段设计：
1. **Secrets 过滤** — 匹配 8 种 regex 模式删除含密钥的记忆
2. **剪枝** — 归档 30 天无访问的条目
3. **去重** — ≥70% 关键词重叠的条目合并
4. **模式提取** — 3+ 条目共享 ≥50% 关键词时生成模式摘要

触发条件：每 5 次对话自动执行（`.dream_counter` 文件计数）。

**核心差距**：
- Dream 是纯关键词启发式（Jaccard 重叠），不调用 LLM 做语义蒸馏
- 没有时间维度分层（today/week/longterm/facts），所有记忆平铺
- 没有指纹缓存，每次 Dream 都重新处理全量数据
- 剪枝是永久删除，没有归档到冷存储

#### 具体改动建议

1. **引入时间分层编译**：在 `engine/memory/` 下新增 `compile.py`，实现 `compile_today()` / `compile_week()` / `compile_longterm()` / `compile_facts()` 四个函数，各自输出到员工目录下的 `memory/today.md` 等文件
2. **加入指纹缓存**：对每层编译的输入计算 MD5 指纹，相同则跳过。指纹文件存放在 `memory/` 目录下
3. **LLM 蒸馏替代关键词合并**：`compile_today()` 和 `compile_week()` 使用 LLM 调用做摘要（可复用 `engine/llm/client.py`），保留 Dream 的纯算法去重作为兜底
4. **改造 `assembler.py`**：在 system prompt 的记忆层，先注入编译后的 `memory.md`，再附加近期原始对话
5. **保留 Dream 做清洗**：Dream 继续负责 secrets 过滤和去重，编译管线负责蒸馏

---

### 3b. EventBus 索引订阅

#### 他们怎么做的

**源文件**: `hub/event-bus.ts` (227 行)

OpenHanako 的 EventBus 实现了 **session-indexed O(relevant) 路由**：

```typescript
// hub/event-bus.ts
class EventBus {
  _subscribers: Map<number, {callback, filter}>    // 全量订阅者
  _globalSubs: Set<number>                          // 无 session 过滤的广播订阅者
  _sessionIndex: Map<string, Set<number>>           // 按 sessionPath 索引

  emit(event, sessionPath) {
    // 只遍历 globalSubs + 匹配 sessionPath 的订阅者
    for (const id of this._globalSubs) notify(id);
    const sessionIds = sessionPath ? this._sessionIndex.get(sessionPath) : null;
    if (sessionIds) { for (const id of sessionIds) notify(id); }
  }
}
```

`subscribe()` 时指定 `filter.sessionPath` 则加入 `_sessionIndex`；否则加入 `_globalSubs`。`filter.types` 数组转为 `Set` 以 O(1) 匹配事件类型。

还支持 **request/handle 模式**（插件间通信）：
```typescript
handle(type, handler, options)   // 注册处理器
request(type, payload, options)  // 发请求，等第一个非 SKIP 的 handler 响应
```
带 30s 超时的 `Promise.race`，多个 handler 按注册顺序尝试。

#### Agent-Smith 目前的做法

**Agent-Smith 没有事件总线**。所有通信都是直接函数调用：
- Server services 直接调用 engine 函数 (`engine_reply`, `engine_reply_stream`)
- 团队消息是 `TeamService` 顺序遍历目标员工逐个调用
- 插件触发是 polling/webhook 推送到 handler，没有统一的消息分发机制

**核心差距**：
- 团队群聊中 N 个员工收到消息时，遍历的是全部成员而非关心该事件的成员
- 没有组件间的解耦通信手段 —— server 直接 import engine，耦合度高
- 插件之间不能互相通信
- 将来增加后台任务（定时提醒、自动化工作流）时没有统一的事件分发基础设施

#### 具体改动建议

1. **在 `engine/` 下新增 `event_bus.py`**：实现 `EventBus` 类，核心数据结构：
   - `_subscribers: dict[int, Subscriber]` — 全量订阅表
   - `_global_subs: set[int]` — 广播订阅者
   - `_session_index: dict[str, set[int]]` — 按 session/employee 索引
2. **事件类型定义**：`EventType` 枚举 — `MESSAGE_RECEIVED` / `TOOL_CALLED` / `MEMORY_UPDATED` / `SKILL_COMPLETED` / `PLUGIN_EVENT`
3. **改造 `TeamService`**：发消息时 `emit(MESSAGE_RECEIVED, session_path=group_id)`，只唤醒订阅了该群组的员工，而非遍历全部成员
4. **改造插件系统**：`PollingTrigger` / `WebhookTrigger` 产生的事件统一通过 EventBus 分发，插件可以订阅其他插件的事件
5. **后续价值**：为定时任务、自动化工作流、Agent 间协作提供统一基础设施

---

### 3c. 插件二级权限模型

#### 他们怎么做的

**源文件**: `core/plugin-manager.ts` (1713 行)

OpenHanako 的插件系统实现了 **restricted / full-access 两级权限**：

```typescript
// core/plugin-manager.ts
const accessLevel = (entry.source === "builtin" || entry.trust === "full-access")
  ? "full-access"
  : "restricted";
```

| 能力 | restricted | full-access |
|---|---|---|
| tools | Yes | Yes |
| skills | Yes | Yes |
| commands (palette 模式) | Yes | Yes |
| commands (slash handler) | **No** | Yes |
| routes (HTTP) | **No** | Yes |
| extensions (Pi SDK) | **No** | Yes |
| providers (LLM) | **No** | Yes |
| pages / widgets / settingsTabs | **No** | Yes |
| lifecycle hooks (onload/onunload) | **No** | Yes |

关键设计：
- **builtin** 插件始终 full-access，不受 disabled 列表约束
- **community** 插件默认 restricted；需要用户全局开关 `allowFullAccessPlugins` 才能提升
- 插件来源优先级: dev(0) > community(1) > builtin(2)，同 id 多来源时按优先级 shadow
- 加载有 15s 超时 (`PluginLoadTimeoutError`)
- 热操作通过 `_opQueue` 序列化 (install/remove/enable/disable)
- 激活由 `activationEvents` 控制 (`onStartup` / `onToolCall:*` / `onBusRequest:*` / `onPageOpen` 等)

插件可贡献 10 种类型：tools / skills / commands / routes / extensions / providers / agents / pages / widgets / settingsTabs。

#### Agent-Smith 目前的做法

**源文件**: `engine/plugin/` (4 个文件, ~252 行)

当前插件系统比较基础：
- `PluginManifest` 只有 trigger_type (polling/webhook/manual) 和 skills 列表
- `PluginRegistry` 扫描目录发现插件，无权限分级
- `loader.py` 用 `importlib.util.exec_module` 直接加载 handler，**无沙盒**
- 没有 enable/disable 开关 —— 所有发现的插件都激活
- 没有生命周期钩子 (init/cleanup)
- manual 触发类型没有实现

**核心差距**：
- 没有权限分级 —— 任何插件都能做任何事
- 没有安全沙盒 —— `exec_module` 直接执行不受限
- 没有热操作支持 —— 需重启才能生效
- 贡献类型单一 —— 只能贡献 handler 和 skills

#### 具体改动建议

1. **在 `PluginManifest` 中增加 `trust_level` 字段**：`"restricted"` (默认) / `"full-access"`
2. **定义能力表**：在 `registry.py` 中定义 `CAPABILITY_TABLE`，restricted 插件只允许注册 tools 和 skills，full-access 允许全部能力
3. **在 `loader.py` 中增加权限检查**：加载 handler 前校验 manifest 的 trust_level，restricted 插件的 handler 不允许 import 敏感模块 (os, subprocess, importlib 等)
4. **增加 enable/disable 开关**：在 `PluginRegistry` 中维护 `disabled_plugins: set[str]`，持久化到 `~/.agent-smith/config.yaml`
5. **增加加载超时**：`load_handler()` 添加 asyncio.wait_for 包装，15s 超时
6. **增加生命周期钩子**：manifest 中声明 `on_load` / `on_unload`，在插件启用/禁用时调用

---

### 3d. Sub-Agent 异步委派

#### 他们怎么做的

**源文件**: `lib/tools/subagent-tool.ts` (500+ 行)

OpenHanako 实现了 **fire-and-forget 非阻塞委派**：

```
调用方 -> 立即返回 taskId/threadId -> 后台隔离 session 执行
-> 完成后 DeferredResultStore 持久化 -> steer 消息回灌主对话
```

核心设计：
- 调用 `subagent` 工具后 **立即返回** taskId 和 threadId，父 Agent 继续工作
- 子任务在独立 session 中执行，不阻塞父级
- 完成后通过 `DeferredResultStore` 持久化结果
- `deferred-result-ext` 以 steer 消息注入父 Agent 的下一轮对话

**并发控制**：
- per-session 最多 10 个并行 subagent (`MAX_PER_SESSION`)
- 全局最多 20 个 (`MAX_GLOBAL`)
- 30 分钟超时 (`SUBAGENT_TIMEOUT_MS`)
- 排队期间不计入超时时间

**权限继承** (Codex 式)：
- `read`: 子 Agent 只读，不能编辑文件或执行 mutating 命令
- `write`: 需要父会话处于可操作模式
- 省略: 继承父会话当前权限档

支持 `agent="?"` 查询团队 Agent 列表，通过 `agent` 参数指定目标 Agent。

#### Agent-Smith 目前的做法

**源文件**: `server/app/services/team_service.py` (196 行)

当前团队协作是 **同步顺序执行**：

```python
# team_service.py — _route_to_employees()
for emp_id in targets:
    reply = await engine_reply(emp_id, ...)  # 阻塞等每个员工回复
    messages.append(reply)
```

**核心差距**：
- 员工逐个串行回复，3 个员工 = 3x 延迟
- 没有 fire-and-forget 模式 —— 父任务必须等子任务完成
- 没有并发限制和超时控制
- 员工之间没有权限隔离

#### 具体改动建议

1. **将顺序调用改为 `asyncio.gather`**：`_route_to_employees()` 中用 `asyncio.gather(*[engine_reply(emp_id, ...) for emp_id in targets])` 并行调用
2. **新增 `engine/execution/subagent.py`**：实现 `SubAgentExecutor` 类
   - `dispatch(parent_session_id, target_employee_id, task) -> task_id` — 立即返回
   - 后台启动独立 session 执行任务
   - 完成后写入 `DeferredResultStore`（可复用 SQLite）
3. **并发控制**：
   - per-session 上限: `MAX_CONCURRENT_PER_SESSION = 5`
   - 全局上限: `MAX_CONCURRENT_GLOBAL = 10`
   - 超时: 30 分钟
4. **结果回灌**：在 `reply()` 入口处检查 `DeferredResultStore`，如有已完成的子任务结果，注入到当前轮对话的 context 中
5. **权限继承**：子 Agent 默认继承父级的工具权限 (`tool_guard` 配置)，支持显式降级为 read-only

---

### 3e. IM 桥接适配器模式

#### 他们怎么做的

**源文件**: `lib/bridge/bridge-manager.ts` (107.9K) + 5 个适配器文件

OpenHanako 实现了 **Adapter Registry 模式**，一个 Agent 可以同时通过多个 IM 平台对外服务：

```typescript
// lib/bridge/bridge-manager.ts
const ADAPTER_REGISTRY = {
  telegram:  { create, getCredentials, ownerSessionKey },
  feishu:    { create, getCredentials, ownerSessionKey, connectsAsync: true },
  dingtalk:  { create, getCredentials, ownerSessionKey, connectsAsync: true },
  qq:        { create, getCredentials, ownerSessionKey },
  wechat:    { create, getCredentials, ownerSessionKey, connectsAsync: true },
};
```

每个平台一个独立 adapter 文件：
- `telegram-adapter.ts` (13.3K) — node-telegram-bot-api
- `feishu-adapter.ts` (28.6K) — @larksuiteoapi/node-sdk
- `dingtalk-adapter.ts` (14.6K) — DingTalk Stream + REST API
- `qq-adapter.ts` (24.4K) — QQ 官方 Bot SDK (含分片上传)
- `wechat-adapter.ts` (23.8K) — 微信机器人 WebSocket

新增平台只需：注册到 `ADAPTER_REGISTRY` + 提供 adapter 文件。

**出站清洗**：Bridge 有三层清洗 (`StreamCleaner` / `_cleanReplyForPlatform` / `_cleanStreamSnapshot`)。核心纪律：**绝不吃正文** —— 成对内省标签 (`mood`/`pulse`/`reflect`/`think`) 连内容删，孤立闭合标签只删 token 本身，code fence 内的字面标签原样保留。

**媒体处理**：每个平台走各自原生接口上传媒体，仅远程 fallback 走 `/api/bridge/media/:token` 临时文件路由。

#### Agent-Smith 目前的做法

Agent-Smith 目前没有 IM 桥接。员工只能通过 macOS App → Server 交互。

`engine/plugin/trigger.py` 中有 `WebhookTrigger` 可以接收外部推送，但这是插件级的事件处理，不是 IM 会话桥接。

#### 具体改动建议

1. **在 `engine/` 下新增 `bridge/` 模块**：
   - `bridge_manager.py` — 管理适配器注册表和生命周期
   - `base_adapter.py` — 定义 `BridgeAdapter` 抽象基类：
     ```python
     class BridgeAdapter(ABC):
         async def connect(self, credentials: dict) -> None
         async def send_message(self, session_id: str, content: str) -> None
         async def receive_message(self) -> AsyncIterator[BridgeMessage]
         async def disconnect(self) -> None
     ```
   - `adapters/feishu.py` — 飞书适配器 (企业场景优先)
   - `adapters/dingtalk.py` — 钉钉适配器
2. **消息标准化**：定义 `BridgeMessage` 数据类 (sender, content, attachments, platform, timestamp)，所有适配器输出统一格式
3. **与 EventBus 集成**：适配器收到消息后 emit `MESSAGE_RECEIVED` 事件，由 EventBus 路由到对应的员工
4. **出站清洗**：在 `bridge_manager.py` 中实现输出清洗，去除内部标签、截断过长回复、适配各平台的消息长度限制
5. **配置存储**：桥接凭证存储在 `~/.agent-smith/config.yaml` 的 `bridges` 节下，按平台分组

---

## 4. 核心区别总结

| 维度 | Agent-Smith | OpenHanako |
|---|---|---|
| **产品定位** | 企业级数字员工工作台 — 员工有模板、有角色边界、有质量门禁 | 个人 AI 陪伴助理 — 强调人格、情感、记忆连续性 |
| **执行模型** | 四层嵌套 (SkillChain DAG → 门禁 → ReAct → 工具调用)，12 个质量门禁 | 单层 ReAct (Pi SDK agent loop)，LLM 自判断质量 |
| **质量保证** | 12 个 regex/启发式门禁 (PlanningGate, DesignGate, TestGate, ValidationGate, ReviewGate, RootCauseGate, SkillRubricGate, GitWorktreeGate, PRGate, TestDeliveryGate 等)，失败触发回溯 | 无显式门禁，依赖 LLM 自我评估 |
| **System Prompt** | 11 层组装 (role→style→workflow→toolbox→skills→capabilities→work_styles→delivery_pipelines→context→output_style→memory→runtime) | 静态前缀 + 动态尾部，优化 prefix cache 命中率 |
| **记忆系统** | Dream 关键词去重 + 30 天剪枝 | 4 层时间蒸馏 + MD5 指纹缓存 + LLM 摘要 |
| **多平台触达** | 仅 macOS App | Telegram / 飞书 / 钉钉 / QQ / 微信 |
| **Agent 模板** | 无代码文件定义 (.md/.yaml/.json)，新加 Agent 不碰代码 | JSON 定义 + identity.md + ishiki.md (意识文件，含人格参数) |

### 各有所长

- **Agent-Smith 优势**：执行质量可控（12 门禁 + 回溯机制），分层架构清晰（五层单向依赖），企业级安全（ToolGuard + secrets 过滤），技能自进化（SkillStore + rubric 评分）
- **OpenHanako 优势**：记忆系统成熟（时间分层 + 指纹缓存），多平台触达（5 IM 桥接），插件生态完整（二级权限 + 10 种贡献类型 + 热操作），异步协作（fire-and-forget subagent）

---

## 5. 不借鉴的部分

### Computer Use (macOS Accessibility API 桌面自动化)

OpenHanako 实现了基于 macOS Accessibility API 的桌面自动化能力，可以控制其他应用窗口、点击按钮、输入文本。这是一个很有想象力的功能，但暂不借鉴，原因：
- 涉及系统级权限申请，安全风险大
- Agent-Smith 的 macOS App 是 SwiftUI 原生应用，已经可以通过 Apple 框架直接集成系统能力
- 桌面自动化的稳定性依赖 UI 结构，容易因应用更新而失效
- 可作为未来独立插件开发，不需要改动核心架构

**状态**: 记录但推迟 (Deferred)

### 人格/角色扮演系统

OpenHanako 有丰富的人格系统 (`identity.md` + `ishiki.md` 意识文件)，支持情感状态、内省标签 (`<mood>`, `<pulse>`, `<reflect>`, `<think>`)。Agent-Smith 定位企业数字员工，不需要拟人化情感：
- 员工角色由 `role.md` + `style.md` 定义，足够覆盖工作场景
- 情感标签会增加 token 消耗且对工作输出没有帮助
- 企业场景更需要可预测性和专业性，而非个性化

**状态**: 不借鉴 (Not applicable)
