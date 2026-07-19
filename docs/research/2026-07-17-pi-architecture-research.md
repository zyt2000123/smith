# Pi 架构调研：一个可扩展本地 Agent Harness 是怎样跑起来的

> 范围：只审阅 `earendil-works/pi` 的一手 GitHub 源码和仓库文档；基线为 `main` 在 `216e672e7c9fc65682553394b74e483c0c9e47f7`（2026-07-16）。本文描述的是该提交的实现，不代表 Agent-Smith 已具备相同能力。

## 结论先行

Pi 的关键不是把一套提示词塞进 CLI，而是明确分成四层：`pi-coding-agent` 负责应用运行时、会话和交互模式；`pi-agent-core` 是无 UI 的事件化 agent loop；`pi-ai` 以统一的流接口封装 provider/auth/model；`pi-tui` 只负责终端渲染与输入。仓库根 README 也将这四个包列为产品边界。[包边界](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/README.md#L305-L324)

```text
pi 命令
  -> CLI / main：参数、session、project trust、runtime
  -> AgentSession：prompt、工具注册、扩展钩子、持久化、压缩
  -> Agent（pi-agent-core）：LLM 流 -> tool calls -> tool results -> 下一轮
  -> ModelRuntime（pi-ai）：认证/headers/model -> 具体 provider stream
  -> AgentSession 事件 -> InteractiveMode（pi-tui）或 print / JSON-RPC
```

## 1. CLI 启动与运行时装配

- npm `bin` 将 `pi` 指向 `dist/cli.js`；薄入口设置进程名、配置 HTTP dispatcher 后调用 `main(argv)`。[package.json](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/package.json#L1-L18)；[cli.ts](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/cli.ts#L1-L18)
- `main()` 先解析参数和模式，再先选定目标 session 的 `cwd`；这样恢复别的项目 session 时，设置、扩展、provider 注册与模型都按**目标 cwd**重建，而不是沿用启动目录。[main.ts](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/main.ts#L566-L675)
- `createAgentSessionServices()` 组合 `ModelRuntime`、`SettingsManager`、`DefaultResourceLoader`；随后 `createAgentSessionFromServices()` 生成 session。最后同一 runtime 按模式进入 `InteractiveMode`、print 或 JSON-RPC，故三种 I/O 不各自实现 agent loop。[services](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/agent-session-services.ts#L103-L184)；[模式分发](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/main.ts#L809-L855)

## 2. Provider 流与 agent loop

1. `createAgentSession()` 创建 `Agent`，注入 `streamFn`；该函数把 timeout、重试、session id、provider attribution 和扩展的请求/响应 hooks 合并后，调用 `modelRuntime.streamSimple()`。[session 装配](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/sdk.ts#L289-L348)
2. `ModelRuntime` 用 `pi-ai` 的 `Models` 聚合 built-in provider、文件配置和扩展 provider；每次请求解析 auth、合并 headers/env，再调该 provider 的 `streamSimple`。它并不让 agent loop 直接认识 OpenAI、Anthropic 等协议。[ModelRuntime 创建](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/model-runtime.ts#L91-L160)；[请求分发](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/model-runtime.ts#L418-L475)；[provider 接口](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/ai/src/models.ts#L91-L168)
3. `runAgentLoop()` 把 user message 加入 context，循环把内部 `AgentMessage[]` 转为 provider `Message[]`，并消费 `start`、文本/thinking/tool-call delta、`done/error` 流事件。最终 assistant message 中若有 tool call，则执行工具、把 tool result 放回 context，继续下一轮；支持 steering 与 follow-up 队列。[主循环](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/agent/src/agent-loop.ts#L100-L276)；[流事件桥接](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/agent/src/agent-loop.ts#L278-L374)
4. 工具批次默认并行；全局设置为 sequential，或某工具声明 `executionMode: "sequential"` 时才串行。参数会先校验，`beforeToolCall` 可拒绝，执行后 `afterToolCall` 可改写结果。[工具调度](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/agent/src/agent-loop.ts#L410-L556)；[校验与 hooks](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/agent/src/agent-loop.ts#L588-L704)

## 3. 工具与权限：可扩展，但默认不是审批型安全模型

- 内置工具集合是 `read`、`bash`、`edit`、`write`、`grep`、`find`、`ls`；默认激活前四个。`--tools`/SDK allowlist 与 exclude list 决定哪些定义进入 agent 的工具表，扩展/SDK 工具通过同一个 registry 包装后再加入。[工具工厂](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/tools/index.ts#L64-L151)；[默认与筛选](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/sdk.ts#L240-L247)；[注册表合并](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/agent-session.ts#L2430-L2520)
- extension 的 `tool_call` hook 是可实现确认、路径保护或策略拒绝的插点，`tool_result` 可变换返回值；它们在 `AgentSession` 中接到 agent 的 before/after tool callbacks。[hook 接线](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/agent-session.ts#L441-L490)
- 但这不是内建的强制 permission/sandbox：官方明确说 builtin tools、extensions 与 shell command 都以启动 `pi` 的用户权限运行；project trust 只防止未批准项目在启动时加载 `.pi` 设置/扩展等资源，**不**限制后续工具能力。真实隔离要交给容器、VM 或 OS sandbox。[安全模型](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/docs/security.md#L1-L68)；[README 的同一说明](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/README.md#L325-L332)

## 4. Context 与 session：树状 JSONL，而非独立“记忆库”

- 每个新 run 的 base prompt 由资源加载器读取全局与 cwd 祖先链中的 `AGENTS.md`/`CLAUDE.md`、skills、选中的工具提示和可选自定义 prompt 组装；因此项目指令是启动/重载 runtime 时读取的资源，而不是一次性写死在 CLI。[context 文件发现](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/resource-loader.ts#L56-L91)；[prompt 重建](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/agent-session.ts#L1009-L1043)
- session 默认写在 `~/.pi/agent/sessions/--<cwd>--/*.jsonl`；每条 entry 带 `id`/`parentId`，所以同一文件可以有树状分支。`message_end` 时 `AgentSession` 立即追加 message/custom message，UI 则订阅同一 `AgentSession` 事件流更新画面。[存储路径与上下文投影](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/session-manager.ts#L440-L480)；[持久化](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/agent-session.ts#L597-L622)；[TUI 订阅](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/modes/interactive/interactive-mode.ts#L2807-L2811)
- 复用 context 时，`buildSessionContext()` 只投影当前 leaf 到根的路径；遇到 compaction entry 时以摘要加保留 entries 代替被压缩历史，`custom` entry 不进入 LLM context，`custom_message` 才会进入。这是会话历史/分支/压缩模型，核心路径里没有语义检索步骤。[投影规则](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/session-manager.ts#L302-L468)；[JSONL 格式说明](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/docs/session-format.md#L1-L50)

## 5. Extensions 与 TUI：同一事件总线的两种消费者

- 扩展是可直接加载的 TypeScript factory（jiti），可注册 tool、slash command、shortcut、flag、消息/entry renderer、provider，并订阅 session、agent、provider 与工具生命周期；全局扩展在 `~/.pi/agent/extensions`，项目 `.pi/extensions` 只在项目被信任后加载，`/reload` 会重建 runtime。[扩展模型与位置](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/docs/extensions.md#L1-L105)；[生命周期顺序](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/docs/extensions.md#L183-L238)
- `DefaultResourceLoader` 负责将 extensions、skills、prompt templates、themes 和 context files 收集为 runtime resources；`AgentSession` 用 `ExtensionRunner` 绑定这些扩展，再将 extension tool 与内置 tool 统一包装。扩展并非 UI 插件层，而是能影响 provider、context、tool 和 session 的运行时插件层。[resource loader](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/resource-loader.ts#L272-L389)；[runtime 构建](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/core/agent-session.ts#L2523-L2575)
- interactive mode 使用自有的 `pi-tui` component/TUI 抽象；它不驱动 LLM，只把 session 事件渲染为 assistant、tool、状态与 editor 组件。print 与 RPC 模式复用同一 `AgentSessionRuntime`，这正是 UI 与 agent runtime 能分离的原因。[TUI 依赖与职责](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/modes/interactive/interactive-mode.ts#L1-L118)；[模式共享 runtime](https://github.com/earendil-works/pi/blob/216e672e7c9fc65682553394b74e483c0c9e47f7/packages/coding-agent/src/main.ts#L809-L855)

## 对实现取舍的准确理解

Pi 的可迁移骨架是「单一 session runtime + 纯事件化 agent loop + provider adapter + extension registry + 多个 I/O front-end」。它的 project trust 对**加载外部项目资源**很有价值；但不要把它误读成工具审批或沙箱系统。若吸收其结构，安全执行边界仍应独立放在每次工具调用的强制 guard/approval 与 OS 级隔离中，而不是只复制 extension hook。
