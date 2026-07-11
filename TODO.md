# Agent-Smith TODO

> 维护规则：完成一项立即勾选；范围、依赖或验收标准变化时同步更新。
> 当前目标：深化单常驻 Agent 运行时，不恢复 `employees` 多角色产品模型。

## 状态

- [x] 完成主流 Agent 设计调研
- [x] 审计当前 Runtime、Tool、Checkpoint、Memory、Event 主路径
- [x] 运行相关基线测试：21 passed
- [x] 完成 engine 宏观设计评审（R1–R8）与内核深查（K1–K6），见下方"设计评审发现"
- [ ] 确认分批交付范围与 Sandbox/UI 边界
- [ ] 完成架构设计并取得确认
- [ ] 编写实施计划

## 设计评审发现（2026-07-10 · engine 宏观 + 内核深查）

> 图解与证据：https://claude.ai/code/artifact/e1368e55-bf8d-4f39-a805-0a72434e2865 （R1–R8 对应评审页 P1–P8）。
> 行号以 2026-07-10 工作区为准。各条标注了与下方 P0/P1 计划的归属关系；标"未覆盖"的是现有计划缺口。

### 高

- [ ] R1 `run_agent` 与 `run_agent_stream` 双实现已漂移（sync 版缺 checkpoint 保存），应收敛为事件流收集器（`execution/agent_loop.py:51/:219`；归属：Agent Loop 状态机）
- [ ] R2 `execute_skill` 用 SKILL.md 替换整个 system prompt，身份/记忆/历史全丢，前序输出以 dict repr 无预算灌入（`skill/executor.py:28`、`agent_loop.py:130`；归属：Context/Session 分离，需补"技能节点上下文交接"验收项）
- [ ] R3 关键词路由独自决定是否进重型链；`route_task_with_llm`（LLM 兜底 + `[direct]` 覆写）全仓库无调用方（`execution/task_router.py:89`、`agent_loop.py:503`；未覆盖）

### 中

- [ ] R4 13 个门禁 11 个纯正则，只读模型自述、不接工具执行事实；rubric 错误词检查惩罚诚实汇报；LLMGate 复核异常静默通过（`execution/gate.py`；可并入回归 Eval 思路）
- [ ] R5 运行时按每条消息重建：MCP stdio 子进程每次 spawn/断开，`RuntimeServices` 生命周期归属需明确决策（`agent_loop.py:466/:679`；归属：ExecutionEnvironment）
- [ ] R6 checkpoint 只写不读，`restore()` 零调用方（`execution/session_state.py`；已由"Agent Loop 状态机与可靠 Checkpoint"覆盖，作为其验收依据）

### 低

- [ ] R7 engine 硬编码 agents 层技能名；技能缺失静默降级为伪技能提示，且两分支上下文构造不一致（`execution/skill_chain.py:70`、`agent_loop.py:117`）
- [ ] R8 三套上下文机制互不知晓；`[0]+[-30:]` 硬截断可能切断 tool_use/tool_result 配对 → API 400（`execution/react_loop.py:125`；归属：Context 预算与 compaction）

### 内核深查（压缩子系统应算进内核验收范围）

> 第一批（内核）已修复并通过测试：engine 全量 53 passed。新增 `test_llm_client.py`，
> 扩充 `test_compression.py`（中文密度、工具证据入摘要）。修复前先写会失败的测试验证。

- [x] 循环骨架判定健康：`react_event_loop` 单一实现 + 三个收集器（`react_loop`/`react_stream_loop`），预算与修复设计无需重构
- [x] K1 token 估算改为 CJK 感知（汉字 1 字符/token，其余 //3），compact 不再在爆窗口后才触发（`execution/compression.py:42`）
- [x] K2 compact 摘要输入纳入工具结果与工具调用意图，压缩不再抹掉任务证据（`compression.py:118-142`）
- [~] K3 prune 单任务内不生效 —— **待决策，暂保持现状**：改动会让模型在任务中途丢失早期工具结果，风险高于收益；K1 修好后 compact 已能在正确时机兜底（`compression.py:62-76`）
- [x] K4 `react_event_loop` 逐条 `dict(m)` 浅拷贝，prune/compress 不再污染调用方 history（`execution/react_loop.py:115`）
- [x] K4.1 流式暂态文本在“长度截断 → 后续工具调用”时会撤回全部未提交 draft 并清空累计文本，避免旧片段被提交或持久化；已补回归测试（`execution/react_loop.py`、`tests/test_react_budget.py`）
- [x] K5 `_request` 4xx（除 429）不再重试，仅 429 与 5xx 重试到上限（`llm/client.py:113-120`）
- [ ] K6 对话中途插入 system 消息 + 裸透传，引擎锁定 OpenAI 兼容协议；换 Anthropic 原生需 client 层适配（记录边界，暂不动）（`react_loop.py:183`、`react_budget.py:84`）

## P0：Rich Tool Contract

- [ ] 为工具定义风险属性：`read_only`、`write`、`destructive`、`external_side_effect`
- [ ] 为工具定义并发属性：`safe`、`serial`
- [ ] 为工具定义审批策略：`never`、`policy`、`always`
- [ ] 为工具定义执行环境：`host`、`sandbox`、`either`
- [ ] 为工具定义 timeout、cancel、idempotency 和结果处理策略
- [ ] 保持现有 `TOOL_META + execute` 工具兼容
- [ ] 让 Registry、Policy、执行器、Trace 和 UI 消费同一份工具元数据
- [ ] 补齐正常、非法配置、兼容和异常路径测试

## P0：Agent Loop 状态机与可靠 Checkpoint

- [ ] 定义显式 `RunStatus` 与合法状态转换
- [ ] 分离 `RunState`、会话历史和 Durable Memory
- [ ] 为每次 run、turn、tool call 分配稳定 ID
- [ ] 在关键状态转换后原子保存 versioned checkpoint
- [ ] 支持完成、失败、取消、阻塞、预算耗尽和等待审批终态
- [ ] 恢复时避免重复执行已经完成的副作用
- [ ] 保持现有 SSE 事件和 SkillChain 行为兼容
- [ ] 补齐状态转换、崩溃恢复、坏 checkpoint 和重复恢复测试

## P0：Permission / Approval / ExecutionEnvironment 分层

- [ ] `ToolPolicy` 只负责 allow、deny、require approval 决策
- [ ] 定义结构化 `ApprovalRequest`、`ApprovalDecision` 和恢复协议
- [ ] 定义小而深的 `ExecutionEnvironment` 接口
- [ ] 实现 `LocalExecutionEnvironment`
- [ ] 确认并实现 Sandbox Adapter 的首期边界
- [ ] 确认 Shell 审批 UI 的首期边界
- [ ] 将 shell/git 等副作用工具接入执行环境，不在工具内自行创建进程
- [ ] 补齐拒绝、审批、取消、超时和环境失败测试

## P1：持久化 Trace 与回归 Eval

- [ ] 定义 run → turn → tool call 层级 Trace Schema
- [ ] 记录耗时、usage、权限、审批、错误、重试和 checkpoint
- [ ] 实现本地 JSONL Trace Store
- [ ] 对敏感参数和输出执行脱敏/截断
- [ ] 建立固定 Eval 数据集和命令行运行入口
- [ ] 覆盖 outcome、trajectory、safety、efficiency、recovery 指标
- [ ] 为 Trace 写入失败设计不阻断主任务的降级行为

## P1：Context / Session / Run State / Memory 分离

- [ ] `PromptAssembler` 只负责本轮模型 Context
- [ ] Session Store 只负责对话历史
- [ ] Run State Store 只负责执行、审批和恢复状态
- [ ] Durable Memory 只保存跨会话事实、偏好和经验
- [ ] 明确四类数据的 ID、生命周期、保留和删除规则
- [ ] 保留当前 project/agent memory scope 与 evidence
- [ ] 增加 Context 预算、渐进加载和 compaction 验收案例
- [ ] 增加错误记忆、过期记忆和检索质量 Eval

## 推荐实施顺序

1. [ ] Rich Tool Contract
2. [ ] Run State 状态机与 Checkpoint
3. [ ] Permission / Approval / ExecutionEnvironment
4. [ ] 持久化 Trace
5. [ ] 回归 Eval Harness
6. [ ] Context / Session / Run State / Memory 完整分离
7. [ ] Sandbox 与 Shell 审批体验增强

## 全局约束

- [ ] 保持依赖方向 `server → engine → common`
- [ ] Router 只做请求解析、调用和响应转换
- [ ] Engine 不依赖 FastAPI、HTTP 或产品实例管理概念
- [ ] 不覆盖或清理当前工作树中的用户改动
- [ ] 所有行为变更遵循测试先行
- [ ] 每个阶段必须通过相关单测、全量测试和运行时验证
- [ ] 没有真实需求前不增加 External Agent Adapter 或常驻多 Agent
