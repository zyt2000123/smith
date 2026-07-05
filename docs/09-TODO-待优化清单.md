# TODO — 待优化清单

## 一、OpenHanako 借鉴项

### OH-1: 记忆编译管线 + 指纹缓存

- [x] **已完成** (2026-07-05)
- **优先级**: P0 — 直接影响 Agent 回复质量和 token 消耗
- **预估工作量**: 3-4 天
- **涉及文件**:
  - 新增 `engine/memory/compile.py` — 四层编译函数
  - 修改 `engine/memory/store.py` — 在 `save_conversation_memory()` 中触发编译
  - 修改 `engine/prompt/assembler.py` — 记忆层改为注入编译后的 `memory.md`
  - 修改 `engine/memory/dream.py` — 保留 secrets 过滤和去重，编译管线负责蒸馏
- **具体改动**:
  1. 实现 `compile_today()` / `compile_week()` / `compile_longterm()` / `compile_facts()` 四个函数，各自输出到Agent目录 `memory/today.md` 等
  2. 每个函数增加 MD5 指纹缓存（输入 session_id + updated_at 的哈希），相同则跳过
  3. `compile_today()` 和 `compile_week()` 使用 LLM 调用做摘要（复用 `engine/llm/client.py`）
  4. `assemble()` 读取四个编译文件拼成 `memory.md`，空栏写占位符
  5. Dream 继续做清洗层（secrets + 去重），编译管线做蒸馏层

---

### OH-2: EventBus 索引订阅

- [ ] **未开始**
- **优先级**: P1 — 解耦组件通信，为后续功能打基础
- **预估工作量**: 2-3 天
- **涉及文件**:
  - 新增 `engine/event_bus.py` — EventBus 核心实现
  - 修改 `server/app/services/team_service.py` — 消息路由改为 emit 事件
  - 修改 `engine/plugin/trigger.py` — 插件事件统一走 EventBus
- **具体改动**:
  1. 实现 `EventBus` 类：`_subscribers` 全量表 + `_global_subs` 广播集合 + `_session_index` 按 session/employee 索引
  2. 定义 `EventType` 枚举：`MESSAGE_RECEIVED` / `TOOL_CALLED` / `MEMORY_UPDATED` / `SKILL_COMPLETED` / `PLUGIN_EVENT`
  3. `subscribe(callback, filter)` — filter 可指定 session_path 和 types
  4. `emit(event_type, data, session_path)` — 只通知 global + 匹配 session 的订阅者
  5. 改造 `TeamService._route_to_employees()` 使用 EventBus 分发
  6. 改造 `PollingTrigger` / `WebhookTrigger` 的事件输出走 EventBus

---

### OH-3: 插件二级权限模型

- [ ] **未开始**
- **优先级**: P1 — 安全基础设施
- **预估工作量**: 2 天
- **涉及文件**:
  - 修改 `engine/plugin/registry.py` — `PluginManifest` 增加 `trust_level` 字段
  - 修改 `engine/plugin/loader.py` — 加载时校验权限 + 增加超时
  - 修改 `engine/plugin/trigger.py` — 增加 enable/disable 支持
  - 新增配置项到 `~/.agent-smith/config.yaml` — `disabled_plugins` 列表
- **具体改动**:
  1. `PluginManifest` 增加 `trust_level: str = "restricted"` 字段
  2. 定义 `CAPABILITY_TABLE`: restricted 只允许 tools + skills；full-access 允许全部
  3. `load_handler()` 增加 `asyncio.wait_for` 超时包装 (15s)
  4. `PluginRegistry` 增加 `disabled_plugins: set[str]`，从 config.yaml 读取
  5. manifest 增加 `on_load` / `on_unload` 生命周期钩子声明

---

### OH-4: Sub-Agent 异步委派

- [ ] **未开始**
- **优先级**: P2 — 提升多 Agent 协作效率
- **预估工作量**: 3-4 天
- **涉及文件**:
  - 新增 `engine/execution/subagent.py` — `SubAgentExecutor` 非阻塞委派
  - 修改 `server/app/services/team_service.py` — 串行改并行 (`asyncio.gather`)
  - 修改 `engine/execution/agent_loop.py` — `reply()` 入口检查 deferred 结果
  - 新增 `engine/memory/deferred_store.py` — 子任务结果持久化
- **具体改动**:
  1. `SubAgentExecutor.dispatch(parent_session_id, target_employee_id, task) -> task_id` — 立即返回
  2. 后台启动独立 session 执行，完成后写入 `DeferredResultStore` (SQLite)
  3. 并发控制: per-session 上限 5，全局上限 10，超时 30 分钟
  4. `reply()` 入口检查 `DeferredResultStore`，有已完成结果时注入 context
  5. `TeamService._route_to_employees()` 改为 `asyncio.gather` 并行调用

---

### OH-5: IM 桥接适配器模式

- [ ] **未开始**
- **优先级**: P3 — 扩展触达渠道，非核心功能
- **预估工作量**: 5-7 天 (每个平台 ~1.5 天)
- **涉及文件**:
  - 新增 `engine/bridge/bridge_manager.py` — 适配器注册表 + 生命周期管理
  - 新增 `engine/bridge/base_adapter.py` — `BridgeAdapter` 抽象基类
  - 新增 `engine/bridge/adapters/feishu.py` — 飞书适配器
  - 新增 `engine/bridge/adapters/dingtalk.py` — 钉钉适配器
  - 修改 `server/app/main.py` — 增加 bridge 相关路由
  - 配置: `~/.agent-smith/config.yaml` 增加 `bridges` 节
- **具体改动**:
  1. 定义 `BridgeAdapter` ABC: `connect()` / `send_message()` / `receive_message()` / `disconnect()`
  2. 定义 `BridgeMessage` 数据类: sender, content, attachments, platform, timestamp
  3. `BridgeManager` 维护 `ADAPTER_REGISTRY` 字典，新平台只需注册 + 写 adapter
  4. 收到消息后 emit `MESSAGE_RECEIVED` 事件 (依赖 OH-2 EventBus)
  5. 出站清洗: 去内部标签、截断过长回复、适配平台消息长度限制
  6. 优先实现飞书 + 钉钉 (企业场景)

---

## 二、现有实现待检查项

> 以下功能已在本轮开发中实现，需要人工走查确认正确性。

### P1: 记忆 Dream 机制 + project 作用域

- [ ] **待检查**
- **涉及文件**:
  - `engine/memory/dream.py` (241 行) — DreamConsolidator 核心逻辑
  - `engine/memory/store.py` — FileMemoryStore + dream_counter 触发
  - `engine/memory/project.py` — project 作用域记忆 (如果存在)
- **检查要点**:
  - [ ] secrets 过滤的 8 个 regex 模式是否覆盖常见泄漏模式 (AWS key, GCP SA key 等)
  - [ ] 30 天剪枝阈值是否合理，是否应该可配置
  - [ ] 70% 关键词重叠去重是否误合并语义不同的条目
  - [ ] `.dream_counter` 文件并发安全性（多 session 同时写）
  - [ ] project 作用域是否正确隔离不同项目的记忆

---

### P2: Git 工具集成 (git_ops)

- [ ] **待检查**
- **涉及文件**:
  - `agents/tools/git_ops.py` — Git 操作工具
  - `engine/execution/agent_loop.py` — 工具注册和调用
  - `engine/safety/tool_guard.py` — Git 命令安全守卫
- **检查要点**:
  - [ ] `git push --force` 等破坏性操作是否被 ToolGuard 拦截
  - [ ] 工作目录是否正确解析（绝对路径 vs 相对路径）
  - [ ] 大仓库的 `git log` / `git diff` 输出是否有截断保护
  - [ ] credentials 是否可能通过 git 命令泄漏

---

### P3: Skill Rubric Gate + DesignGate

- [ ] **待检查**
- **涉及文件**:
  - `engine/execution/gate.py` (452 行) — 9 个门禁实现
  - `engine/execution/skill_chain.py` (77 行) — SkillChain + backtrack_map
  - `engine/execution/backtrack.py` (36 行) — FailureLoopGuard
- **检查要点**:
  - [ ] `SkillRubricGate` 的 regex 匹配是否会误判（包含正确关键词但内容不佳的输出通过门禁）
  - [ ] `DesignGate` 的条件触发 (`_needs_architecture` 用 regex 数文件引用) 是否可靠
  - [ ] 回溯机制 (`backtrack_map`) 是否可能导致无限循环
  - [ ] `FailureLoopGuard` 的 `max_same=2` / `max_strategies=2` 参数是否合理
  - [ ] 所有 9 个 Gate 的通过条件是否过松或过严

---

### P4: 技能自进化 (SkillStore + skill_manage)

- [ ] **待检查**
- **涉及文件**:
  - `engine/skill/store.py` — SkillStore 技能存储
  - `engine/skill/skill_manage.py` — 技能管理 (安装/卸载/升级)
  - `engine/skill/rubric.py` — 技能评分 rubric
  - `agents/skills/` — 内置技能目录
- **检查要点**:
  - [ ] 技能安装是否有来源验证（防止恶意技能注入）
  - [ ] 技能自进化的评分阈值是否合理
  - [ ] 技能版本管理是否支持回滚
  - [ ] Agent自装技能 (`~/.agent-smith/employees/<id>/skills/`) 与内置技能的优先级
  - [ ] 技能依赖关系是否被正确处理

---

### P5: 用户偏好自动学习 (UserPreferenceLearner)

- [ ] **待检查**
- **涉及文件**:
  - `engine/memory/user_learner.py` (230 行) — UserPreferenceLearner
  - `agents/templates/*/context.md` — `{{to_be_learned}}` 占位符
- **检查要点**:
  - [ ] 3 次观察 (`_CONFIDENCE_THRESHOLD`) 确认偏好是否足够可靠
  - [ ] regex/keyword 启发式检测语言、verbosity、tech_level 是否准确
  - [ ] 写入 `context.md` 时是否只替换 `{{to_be_learned}}` 占位符，不覆盖用户手写内容
  - [ ] 是否有机制让用户纠正错误的自动学习结果
  - [ ] 多语言场景 (中/日/英混用) 的语言检测是否稳定

---

### P6: 插件系统 (框架 + GitHub webhook)

- [ ] **待检查**
- **涉及文件**:
  - `engine/plugin/registry.py` (92 行) — PluginManifest + PluginRegistry
  - `engine/plugin/loader.py` (42 行) — 动态加载 handler
  - `engine/plugin/trigger.py` (108 行) — PollingTrigger + WebhookTrigger
  - `server/app/routers/` — webhook 路由 (如果存在)
- **检查要点**:
  - [ ] `exec_module` 动态加载 handler 是否有安全隐患（代码注入、路径穿越）
  - [ ] `PollingTrigger` 的 asyncio.Task 是否有正确的异常处理和清理
  - [ ] `WebhookTrigger` 的 payload 是否有签名验证 (GitHub webhook secret)
  - [ ] manual 触发类型是否有实现（当前只是标签）
  - [ ] 插件发现扫描是否只扫描预期目录，防止意外加载

---

### P7: 多 Agent 协作 (团队群聊)

- [ ] **待检查**
- **涉及文件**:
  - `server/app/services/team_service.py` (196 行) — TeamService
  - `server/app/domain/team.py` — Pydantic 模型
  - `server/app/infrastructure/repositories/team_repo.py` — SQLite 持久化
  - `server/app/routers/` — 群聊路由
- **检查要点**:
  - [ ] Agent顺序回复的延迟是否可接受（3 个Agent = 3x LLM 调用时间）
  - [ ] `@employee_id` 提及提取是否可靠（目前是简单字符串匹配）
  - [ ] 最近 20 条消息作为上下文是否足够 / 是否会超出 token 限制
  - [ ] SSE 流式输出中多个 Agent 交替输出时前端显示是否正确
  - [ ] 群聊消息的持久化是否有并发写入问题
  - [ ] 删除群组时关联消息是否被清理

---

## 三、已知技术债务

### TD-1: macOS App 未提交改动

- [ ] **待处理**
- **详情**: `app/` 的 UI 改动在 git stash 里，需要 Xcode 编译才能验证
- **操作**:
  1. `git stash list` 检查 stash 内容
  2. `git stash pop` 恢复改动
  3. 在 Xcode 中打开 `app/AgentSmith.xcodeproj`，编译验证
  4. 确认无误后提交

---

### TD-2: 根目录测试/调试文件清理

- [ ] **待处理**
- **详情**: 根目录下有多个未跟踪的测试和调试文件，应清理或移入测试目录
- **文件列表**:
  ```
  DEBUG_REPORT.md
  browser_test.js
  debug_login_analysis.js
  login.html / login_fixed.html
  login_bug_report.md
  test_email_bug_reproduce.html / test_email_fix.py / test_email_validation.html
  test_login_page.html / test_login_validation.py
  test_regression.py / test_regression_login.html
  validate_login_fix.html / verify_fix.py
  ```
- **操作**: 确认这些文件不再需要后删除，或移入 `tests/` 目录

---

### TD-3: 文档与代码同步检查

- [ ] **待处理**
- **详情**: `docs/` 下 11 篇设计文档与实际代码实现可能存在偏差
- **重点检查**:
  - [ ] `docs/10-Agent执行引擎设计.md` 与 `engine/execution/` 实际实现是否一致
  - [ ] `docs/11-整体架构与设计思路.md` 中的架构图是否反映当前五层结构
  - [ ] `docs/09-架构设计规范.md` 中的约定是否被代码遵守

---

### TD-4: 流式回复记忆保存缺陷

- [ ] **待修复**
- **详情**: `engine/execution/agent_loop.py` 中的 `reply_stream()` 保存对话记忆时传入空字符串
- **涉及文件**: `engine/execution/agent_loop.py` — `reply_stream()` 函数
- **修复方案**: 在流式生成过程中累积完整回复文本，流结束后用完整文本调用 `save_conversation_memory()`

---

### TD-5: import 路径脆弱性

- [ ] **待修复**
- **详情**: `engine/execution/agent_loop.py` 的 `reply()` 函数使用 `sys.path.insert(0, ...)` 动态修改模块搜索路径
- **涉及文件**: `engine/execution/agent_loop.py`
- **风险**: 多次调用可能导致 `sys.path` 膨胀，模块查找不稳定
- **修复方案**: 改为在 `pyproject.toml` 中配置包依赖，或使用 `importlib` 绝对路径导入

---

### TD-6: 流式技能链降级

- [ ] **待修复**
- **详情**: `reply_stream()` 在技能链模式下退化为非流式 —— 先执行完整个链，最后 `yield result`
- **涉及文件**: `engine/execution/agent_loop.py` — `reply_stream()` 的技能链分支
- **修复方案**: 使用 `engine/execution/events.py` 定义的结构化事件类型，将 `run_agent` 改为 async generator 输出 `ExecutionEvent`

---

## 四、后续功能规划

### F-1: 技能市场

- [ ] **规划中**
- **优先级**: P2
- **预估工作量**: 5-7 天
- **设计思路**:
  1. **v1**: GitHub 仓库存放社区技能，`skill install <url>` 下载到Agent skills 目录
  2. **v2**: 独立市场服务，支持搜索/评分/版本管理
  3. **v3**: 根据角色和任务类型自动推荐技能
- **涉及文件**:
  - 新增 `engine/skill/market.py` — 市场客户端
  - 修改 `agents/tools/skill_manage.py` — 增加 `install_from_url`
  - 修改 `server/app/routers/` — 市场代理 API

### F-2: 多 Agent 编排引擎

- [ ] **规划中**
- **优先级**: P2
- **设计思路**: Leader-Worker 模式 + 任务依赖图 + 并行执行 + 结果汇总
- **涉及文件**: 新增 `engine/execution/orchestrator.py`

### F-3: Worktree 强制工作流

- [ ] **规划中**
- **优先级**: P2
- **设计思路**: 技能链第一步自动创建 worktree，禁止主分支直接修改，PR 后自动清理
