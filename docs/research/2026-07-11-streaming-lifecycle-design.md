# Agent-Smith 流式运行终态设计调研：`finish_reason`、SSE 与截断恢复

> 调研日期：2026-07-11  
> 范围：评估当前 `finish_reason → 有界续写 → agent 终态 → SSE done(status)` 修复，与公开的一手 LLM/Agent 流式接口对照。  
> 方法：只引用官方 API/SDK 文档；不推断 ChatGPT、Claude 或其他闭源产品的内部实现。
>
> 实施更新：同日已完成本文建议的第一项演进——活跃 ReAct、技能链和强制技能都会消费 typed Provider events；`AgentRunStream.stream_events()` 在持久化和资源关闭后才给出最终状态。断线重放与持久 `run_id` 仍未实现。

## 一、结论先行

**这是合格的第一阶段修复，但不是成熟流式架构的终局。**

它修掉了最危险的静默失败：模型已经明确表示输出因长度限制而未完成，系统却把半截答案当成成功答案交付。当前实现把这个信号带进 Agent loop，最多续写两次，仍未完成就明确交付 `incomplete`；同时把服务端异常映射为 `failed`，而不是让浏览器只看到连接突然结束。

这与公开的主流接口在**语义**上是一致的：OpenAI Responses 区分 `response.completed`、`response.incomplete` 与 `response.failed`；Anthropic 在流结束前给出 `stop_reason`，并要求调用方根据 `max_tokens` 决定续写或调整限制；Vercel AI SDK 把不同 Provider 的结束原因统一为 `finishReason`，但也保留原始原因。[OpenAI Responses streaming events](https://platform.openai.com/docs/api-reference/responses-streaming/response/refusal/delta?lang=curl) [Anthropic stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons) [Vercel AI SDK `streamText`](https://ai-sdk.dev/docs/reference/ai-sdk-core/stream-text)

但“别家也这么做”不等于“它们都用同一段 Fetch SSE 代码”。公开资料显示，成熟实现共同拥有的是**显式的运行终态、结构化事件、可恢复状态和完成后的清理语义**；SSE、WebSocket、SDK `AsyncIterable` 都可能只是最外层的传输适配器。

## 二、当前实现已经做对了什么

| 层级 | 当前 Agent-Smith 行为 | 判断 |
| --- | --- | --- |
| Provider 响应 | `ChatResponse` 保留兼容 Chat Completions 响应的 `finish_reason`。 | 正确：不要只拿 `message.content`，应保留结束原因。 |
| Agent loop | 非工具调用的文本若是 `finish_reason == "length"`，累积已有文本并最多续写两次；仍超限时发出 `INCOMPLETE(reason="model_output_limit")`。 | 正确的有界恢复：避免无限循环，也不把半截结果伪装成完成。 |
| 引擎边界 | 预算耗尽、模型长度限制、引擎异常都有显式的 `INCOMPLETE`/`FAILED` 事件。 | 正确：把“显示了一些文字”与“run 成功完成”分开。 |
| Server SSE | `stream_message` 最终发出 `done`，携带 `completed`、`incomplete` 或 `failed`。 | 正确：终包是状态，不只是 EOF。 |
| Shell | Fetch 的 `ReadableStream` 解析命名 SSE 事件；缺失 `done` 被当作异常，非 `completed` 会显示警告。 | 正确：前端不再把正常断流误判为成功。 |

这一点很关键：**Fetch SSE 不是解决截断本身的方案。** 在这里它是“用 `fetch` 发起 POST、再手动读取 `ReadableStream` 里的 SSE 帧”的传输实现；它能把服务器的 `incomplete`/`failed` 交给 UI，但不能替 Provider 判断模型是否被截断，也不能凭空让断线后的 run 变得可恢复。

## 三、公开成熟接口实际表达的模式

### 1. 终态不是一个裸 `done` 字符串

OpenAI Responses 的流式 API 会把 `response.completed`、`response.incomplete` 和 `response.failed` 作为不同的终态事件。`response.incomplete` 的 Response 对象含 `status: "incomplete"` 与 `incomplete_details.reason`（示例为 `max_tokens`）。这说明“流结束”与“业务成功”是两回事。[OpenAI Responses streaming events](https://platform.openai.com/docs/api-reference/responses-streaming/response/refusal/delta?lang=curl)

OpenAI Realtime 进一步把这条原则写得很直白：`response.done` 无论最终状态都会出现，客户端仍必须检查 `status` 是 `completed`、`cancelled`、`failed` 还是 `incomplete`。[OpenAI Realtime `response.done`](https://platform.openai.com/docs/api-reference/realtime-server-events/response/mcp_call/in_progress?lang=node)

**对本项目的影响：** 当前 `done.status` 是正确方向；后续应把 `cancelled` 也作为一等终态，而不是把客户端主动取消混成网络错误或没有 `done`。

### 2. 截断原因必须随流或响应返回，而非由文本猜测

Anthropic 的流式 Messages API 有明确的事件顺序：`message_start`、内容块增量、`message_delta`（其中携带最终 `stop_reason`）以及 `message_stop`。其 stop-reason 文档明确规定 `max_tokens` 代表达到输出上限，调用方可提高上限或继续响应；`tool_use` 则是另一种语义，不能当成自然文本结束。[Anthropic streaming messages](https://platform.claude.com/docs/en/build-with-claude/streaming) [Anthropic stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons)

Vercel AI SDK 的 `streamText` 将 Provider 差异规范为 `finishReason`（含 `stop`、`length`、`content-filter`、`tool-calls`、`error`、`other`），并同时暴露 `rawFinishReason`；它的 `onFinish` 在模型响应及本地工具执行完成后才调用。[Vercel AI SDK `streamText`](https://ai-sdk.dev/docs/reference/ai-sdk-core/stream-text)

**对本项目的影响：** 当前只在“无工具调用 + `length`”时续写是谨慎且合理的。不要把 `tool_calls`、内容过滤、拒绝、上下文超限或网络错误都压成一个 `length` 分支。`MAX_LENGTH_CONTINUATIONS = 2` 是本项目的产品/成本策略，不是行业标准；应做成可配置项并记录命中率、续写成功率、额外 token 和重复率。

### 3. 文本 token 流不等于 Agent run 流

OpenAI Agents SDK 将流区分为原始模型事件、语义化 run-item 事件和 Agent 切换事件。文档要求持续消费事件直到迭代器结束，因为最后一个可见文本 token 后仍可能有 session 持久化、审批状态或历史压缩等后处理；结束后才能用 `is_complete` 判断 run 是否真正完成。[OpenAI Agents SDK streaming](https://openai.github.io/openai-agents-python/streaming/) [OpenAI Agents SDK results](https://openai.github.io/openai-agents-python/results/)

该 SDK 还把工具审批建模为 interruption：流结束后取出 `interruptions`，将结果转为 `RunState`，批准或拒绝后恢复同一次 run，而不是重新提交一条用户消息。[OpenAI Agents SDK streaming](https://openai.github.io/openai-agents-python/streaming/)

**对本项目的影响：** 结构化的 Provider/Agent run 事件现已贯穿 `engine → server → shell`；下一层是可恢复状态，而不是仅把现有只产出字符串的 `stream_final_text` 接到 HTTP 上。

## 四、与成熟方案的差距（也是下一阶段边界）

### 1. Provider 已有结构化上游流，但 run 状态还未持久化

当前活跃路径通过 `LLMClient.chat_events()` 把 OpenAI-compatible SSE 规范为 Provider event，再由 `react_event_loop` 转成语义化 Agent event。若 Provider 在发送任何事件前拒绝流式请求，才安全回退到既有 `chat()`；一旦已有 delta，断流会显式失败而不是重放请求。`stream_final_text` 保留为旧的文本适配器，不是活跃协议。

当前事件契约为：

```text
ProviderEvent
  = ResponseCreated | OutputTextDelta | ReasoningDelta
  | FunctionCallArgumentsDelta | Usage | ResponseCompleted(reason, raw_reason)

AgentRunEvent
  = RawResponseEvent | TextDelta | Thinking | ToolStarted | ToolFinished
  | Usage | RunStarted | RunFinished(status, reason)
```

Provider 适配层负责把 OpenAI 的 `finish_reason`、Responses 的 `incomplete_details`、Anthropic 的 `stop_reason` 等映射到统一语义，同时保留原始值用于诊断。Agent loop 只消费统一终态，不直接写 Provider 字符串分支。

### 2. 当前终态可见，但还不是持久、可回放的 run 状态

`done.status` 只在连接仍存活时送到本次 Fetch 请求。若客户端已断连，它不能被送达；现在也没有暴露 `run_id`、事件序号、重连游标或“查询该 run 最终状态”的接口。

这不是 P0 必需功能：对本地短任务，显式失败和已生成部分落库已经比静默断流好得多。若要支持长任务、页面重载、移动网络或跨进程恢复，才应增加：

1. 创建持久 `run_id`，保存 `queued/running/completed/incomplete/failed/cancelled`；
2. 给每个事件 `event_id`/递增序号，保存必要的可展示事件；
3. SSE 断线后按游标重放，或由客户端先查询 run 终态；
4. 工具调用用 call ID 与幂等语义保护，避免“重连即重跑副作用”。

这和 OpenAI Agents SDK 的 `RunState`/interruption 恢复模型在方向上相同，但不要求复制它的具体 API。[OpenAI Agents SDK streaming](https://openai.github.io/openai-agents-python/streaming/)

### 3. 需要把“完成”定义为状态机，而非 transport 收尾

建议最终的运行状态至少为：

```text
running
  ├─ completed
  ├─ incomplete(reason = model_output_limit | budget | content_filter | ...)
  ├─ failed(reason = provider | tool | internal | persistence | ...)
  ├─ cancelled(by = client | server | policy)
  └─ interrupted(waiting_for = approval | resumable_checkpoint)
```

SSE 的 `done` 只是把这一状态机的终态投递给当前观察者；它不应成为状态的唯一来源。

## 五、建议的推进顺序

1. **保留本次修复并观测。** 对 `finish_reason`、续写次数、最终状态、重复文本比率、额外 token、客户端缺失 `done` 建立结构化日志/指标；先确认真实命中率，再决定默认上限是否为 2。
2. **规范化 Provider 终态。** 明确每个已支持 Provider 的 `stop/length/tool_call/content_filter/error` 映射和测试夹具；未知值必须安全地落到非成功终态或可观察的 `other`，不能默认成功。
3. **已完成：真正的上游流。** typed Provider/Agent events 已适配为现有 Fetch SSE；文本 delta 可以即时到达 Shell，且语义 final text 不会被重复发送。`stream_final_text` 仍是兼容适配器，后续可删除而不是接成第二套协议。
4. **按产品需要加入 run 持久化与恢复。** 只有任务会跨连接/跨进程/长时间运行时，才投入持久 `run_id`、事件日志、重放、checkpoint 和幂等工具调用。

## 六、最终判断

**是好的方案吗？** 是，作为第一阶段，它以很小的改动补上了生产系统最需要的“不可静默成功”保证，而且没有为了“真流式”而仓促改变工具调用循环。

**类似产品也是这样做吗？** 它们公开出来的共同做法是：读取模型终止原因、区分 `completed/incomplete/failed`、在最后文本 token 后仍等待 run 真正收尾、把审批/取消/恢复视为状态机问题。它们不一定使用相同的 Fetch SSE 形式，更不会仅凭一个字符串 `done` 判断成功。

所以当前设计应被定位为：**正确的完整性补丁 + 已落地的 typed run-event 流式层**；还不是具备持久运行状态、断线恢复与审批中断的最终运行时。
