# 11 · Agent 设计文档

> **定位**：本文是 Agent-Smith 自研 Agent 框架的**设计规格书**——完整描述概念模型、每个子系统的设计、接口约定、数据流与扩展点。
>
> 与其他文档的分工：
> - `03-Agent执行引擎.md` —— 执行引擎的实现讲解
> - `10-自研Agent框架深度解析.md` —— 设计理念 WHY + 框架对比 + 面试问答
> - **本文（11）** —— 设计规格：是什么、怎么设计的、约定是什么、如何扩展
>
> 所有描述均以当前代码为准（引用形如 `engine/execution/agent_loop.py:31`）。

---

## 目录

1. [设计目标与核心哲学](#一设计目标与核心哲学)
2. [概念模型](#二概念模型)
3. [总体架构与一次对话的生命周期](#三总体架构与一次对话的生命周期)
4. [Agent 身份设计（人格层）](#四 Agent 身份设计人格层)
5. [System Prompt 组装设计](#五system-prompt-组装设计)
6. [执行引擎设计](#六执行引擎设计)
7. [记忆系统设计](#七记忆系统设计)
8. [工具系统设计](#八工具系统设计)
9. [技能系统设计](#九技能系统设计)
10. [插件系统设计](#十插件系统设计)
11. [安全设计](#十一安全设计)
12. [配置体系](#十二配置体系)
13. [服务端集成契约](#十三服务端集成契约)
14. [设计权衡与已知局限](#十四设计权衡与已知局限)
15. [附录：文件地图](#附录文件地图)

---

## 一、设计目标与核心哲学

### 1.1 产品命题

Agent-Smith 交付的不是"聊天机器人"，而是**本地 Agent**：

- **有身份**：每个 Agent 有明确的角色、原则、风格、工作流，而不是一个万能助手
- **有过程**：复杂任务走强制的技能链（规划 → 测试策略 → 验证 → 评审），每步有质量门禁
- **有成长**：记忆会积累、编译、遗忘；偏好会被自动学习；技能可以自装自改
- **有边界**：破坏性操作被规则层拦截，产出必须带证据才能通过门禁

### 1.2 核心哲学：宏观确定性，微观自由度

框架的所有设计都源自一个判断：**LLM 有创造力但不可靠，代码可靠但没创造力**。因此把两者各放在擅长的位置：

| 由代码控制（确定性） | 由 LLM 控制（自由度） |
|---|---|
| 任务路由（走哪条链） | 理解需求、拆解问题 |
| 技能链顺序（先规划后编码） | 每一步内怎么思考 |
| 质量门禁（产出必须有证据） | 选什么工具、传什么参数 |
| 失败回退（退到哪个节点） | 怎么组织回复 |
| 安全拦截（什么命令不能跑） | 换什么方案绕开失败 |

对应到代码就是**四层嵌套执行模型**（见第六章）：

```
任务路由 (task_router)          ← 规则决定走哪条路
  └─ 技能链 DAG (skill_chain)    ← 代码决定步骤顺序 / 门禁 / 回退
       └─ ReAct 循环 (agent_loop) ← LLM 在单步内自由思考-用工具-观察
            └─ 安全护栏 (tool_guard) ← 每次工具调用前的规则拦截
```

### 1.3 三条不可违背的架构约束

1. **依赖单向**：`app → server → engine → common`，engine 不知道 HTTP，common 不知道业务
2. **内容与代码分离**：新增一个 Agent 角色只改 `agents/` 下的 md/yaml/json，不碰任何 Python
3. **模板只读**：`agents/templates/` 由 Git 跟踪、永不被运行时修改；运行时读写的是 `~/.agent-smith/` 下的副本

---

## 二、概念模型

### 2.1 实体一览

| 概念 | 是什么 | 存在哪 | 生命周期 |
|---|---|---|---|
| **Template（模板）** | 角色的出厂定义（9 个文件） | `agents/templates/<role>/` | Git 跟踪，只读 |
| **Employee（Agent）** | 模板的运行实例 + 运行时积累 | `~/.agent-smith/employees/<id>/` | 创建时从模板复制，随使用成长 |
| **Session（会话）** | 一次对话上下文 | SQLite + `employees/<id>/sessions/` | 用户创建/归档 |
| **Task（任务）** | 一条用户消息经路由后的执行单元 | 内存中（TaskType） | 单次执行 |
| **Skill（技能）** | 一段"怎么做某类事"的方法论（SKILL.md） | 内置 `agents/skills/` / Agent 自装 `employees/<id>/skills/` | 内置只读；自装可编辑、带版本 |
| **Tool（工具）** | 一个可被 LLM 调用的原子能力（Python 函数） | `agents/tools/*.py` + MCP 外接 | 启动时注册 |
| **Plugin（插件）** | 外部事件源 + 处理器（如 GitHub、日报） | `agents/plugins/<name>/` | 服务启动时发现、触发器常驻 |
| **Memory（记忆）** | Agent 的经验积累（条目 + 编译层） | `employees/<id>/memory/` | 持续写入、周期编译与遗忘 |
| **Gate（门禁）** | 一段产出的质量检查器 | `engine/execution/gate.py` | 每个技能链节点绑定一个 |
| **SkillChain（技能链）** | 带门禁和回退边的技能 DAG | `engine/execution/skill_chain.py` | 按任务类型构建 |

### 2.2 实体关系

```
Template ──(创建时复制)──▶ Employee ──(1:N)──▶ Session ──(1:N)──▶ Message
                              │
              ┌───────────────┼───────────────┬──────────────┐
              ▼               ▼               ▼              ▼
           Memory          Skills(自装)     config.yaml    context.md
        (积累+编译+遗忘)   (版本化可编辑)   (Agent 级LLM覆盖)  (用户偏好,自动学习)

用户消息 ──route──▶ TaskType ──▶ SkillChain(feature/bugfix) 或 DIRECT
                                    │
                             SkillNode × N ──每节点──▶ Skill + Gate (+ 回退边)
                                    │
                              ReAct 循环 ──▶ Tool 调用 ──ToolGuard──▶ 执行
```

### 2.3 数据目录（运行时的"Agent 档案柜"）

```
~/.agent-smith/
├── config.yaml                     # 平台级配置（LLM key/url/model）
├── employees/<id>/
│   ├── role.md / style.md / workflow.md / toolbox.md   # 人格（从模板复制）
│   ├── context.md                  # 用户偏好（含 {{to_be_learned}} 占位符，自动填充）
│   ├── config.yaml                 # Agent 级 LLM 覆盖 / mcp_servers / tools.enabled
│   ├── expertise.json / traits.json / pipeline.json    # 结构化人格
│   ├── memory/
│   │   ├── recent.jsonl            # 原始对话流水
│   │   ├── agent/*.md  project/*.md # 记忆条目（YAML frontmatter）
│   │   ├── today.md / week.md / longterm.md / facts.md  # 四层编译产物
│   │   ├── .fp_today 等            # 编译指纹缓存
│   │   ├── .dream_counter          # Dream 触发计数
│   │   └── search.sqlite           # FTS5 + sqlite-vec 混合检索索引
│   ├── skills/<name>/SKILL.md      # 自装技能（.versions/ 下保留 10 个历史版本）
│   ├── sessions/.state/<sid>.json  # 执行断点（checkpoint）
│   └── .learner_state.json         # 偏好学习置信度计数
└── sqlite/agent-smith.sqlite       # 索引库（Agent/会话/消息，WAL）
```

---

## 三、总体架构与一次对话的生命周期

### 3.1 五层架构

```
┌─────────────────────────────────────────────────────┐
│ app/        SwiftUI 原生前端（HTTP + SSE）           │
├─────────────────────────────────────────────────────┤
│ server/     FastAPI 平台层                           │
│   routers(薄壳) → services(编排) → infrastructure(仓储) │
├─────────────────────────────────────────────────────┤
│ engine/     自研 Agent 框架（本文主体）               │
│   execution │ prompt │ memory │ llm │ tool │ skill │ plugin │ safety │
├─────────────────────────────────────────────────────┤
│ agents/     纯内容层：模板/技能/工具/插件/安全规则     │
├─────────────────────────────────────────────────────┤
│ common/     配置合并 / SQLite / 文件系统 / 日志       │
└─────────────────────────────────────────────────────┘
```

engine 内部模块与依赖：

```
execution ──▶ llm, prompt, skill, tool, safety, memory
prompt    ──▶ memory.compile（读编译产物）
skill     ──▶ tool（executor 里执行工具调用）
tool      ──▶ (无内部依赖；MCP 为外部进程)
memory / safety / plugin ──▶ 互不依赖
```

### 3.2 一次对话的完整生命周期（流式）

入口：`server/app/services/session_service.py:56` → `engine/execution/agent_loop.py:581`

```
1. app 发 POST /sessions/{id}/messages/stream
2. SessionService 校验会话、落库用户消息
3. engine.reply_stream(employee_id, name, message):
   a. resolve_llm_config() 五级合并配置 → build_llm_client()
   b. ToolRegistry.load_providers(agents/tools/)     ← 扫描注册内置工具
   c. 读 Agent config.yaml 的 mcp_servers → MCPClient 连接 → 注册 mcp_* 工具
   d. SkillRegistry.load_builtin() + load_employee_skills()
   e. PromptAssembler.assemble()                     ← 12 段 system prompt
   f. route_task(message) → DIRECT / FEATURE / BUGFIX
   g. 构建 SkillChain（或 None）、FailureLoopGuard、ToolGuard
4. run_agent_stream() 产出 ExecutionEvent 流：
   ROUTE_DECIDED → (SKILL_START → 工具事件… → GATE_RESULT → SKILL_END)* → TEXT_DELTA → DONE
5. reply_stream 把事件翻译成文本块 yield 给 SessionService
6. SessionService 逐块下发 SSE，结束后整条落库
7. finally: UserPreferenceLearner.observe() 学习偏好；llm.close()
```

非流式路径（`reply`, `agent_loop.py:496`）额外做：`save_conversation_memory()` 写记忆 + 每 5 次触发 Dream 整理和四层编译。

---

## 四、Agent 身份设计（人格层）

### 4.1 设计原则：文件即人格

一个角色 = 一个目录下的 9 个纯文本文件。**不需要写任何代码**，server 自动扫描发现新模板。这样做的理由：

- 人格是内容问题不是代码问题——产品/运营可以直接改
- Git 天然提供人格的版本管理和 review 流程
- Prompt 组装器按固定顺序读文件，新角色零接入成本

### 4.2 模板文件规格

| 文件 | 角色 | 内容约定 | 示例（backend-engineer） |
|---|---|---|---|
| `role.md` | **身份**（我是谁） | Core Mission / Non-Negotiable Principles / Done Criteria / Anti-Goals 四段 | "数据完整性第一：所有写操作必须有事务保护"；Anti-Goals 明确"不做前端页面" |
| `style.md` | **风格**（我怎么说话） | 沟通语气、汇报格式 | — |
| `workflow.md` | **工作流**（我怎么干活） | 任务评估表 + **强制技能链**（可被引擎解析，见 6.3） | `planning → architecture(仅大型变更) → testing-strategy → change-validation → code-review` |
| `toolbox.md` | **工具观**（我用什么） | 工具使用原则；运行时追加实际注册的工具清单 | — |
| `context.md` | **用户上下文** | 用户偏好；`{{to_be_learned}}` 占位符标记可学习字段 | 由 UserPreferenceLearner 自动填充 |
| `config.yaml` | **配置** | name/role/description、LLM 覆盖、`tools.enabled` 白名单、`mcp_servers` | `model: null` 表示继承上层 |
| `expertise.json` | **能力清单**（结构化） | `[{name, description}]` | "api-development: RESTful/GraphQL API 设计…" |
| `traits.json` | **风格标签**（结构化） | 字符串数组 | `["system-thinking", "contract-driven", ...]` |
| `pipeline.json` | **交付承诺**（结构化） | 按 task_type 列出交付流水线 | feature: `define-api-contract → … → pr-with-test-report` |

md 与 json 的分工：**md 写给 LLM 读**（自然语言指令），**json 写给代码读**（可被格式化、可被 UI 展示、可被裁剪）。

### 4.3 Agent 生命周期

```
创建：agents/templates/<role>/ ──复制──▶ ~/.agent-smith/employees/<id>/
运行：只读写副本；模板永不被触碰
成长：memory/ 积累+编译；skills/ 自装；context.md 被 learner 填充
删除：删目录 + SQLite 记录
```

模板升级不影响已创建 Agent（各自独立演化）；这是有意为之——Agent 的"成长痕迹"比模板一致性更重要。

---

## 五、System Prompt 组装设计

实现：`engine/prompt/assembler.py:42`（`PromptAssembler.assemble`）

### 5.1 12 段分层结构

按固定顺序拼接（`\n\n---\n\n` 分隔），空段过滤：

| # | 段 | 来源 | 稳定性 | 被裁剪优先级* |
|---|---|---|---|---|
| 0 | 身份 role | `role.md` | 稳定 | **永不裁剪** |
| 1 | 风格 style | `style.md` | 稳定 | 9（最后裁） |
| 2 | 工作流 workflow | `workflow.md` | 稳定 | **永不裁剪** |
| 3 | 工具 toolbox | `toolbox.md` + ToolRegistry 实时清单 | 稳定 | 8 |
| 4 | 技能清单 skills | SkillRegistry 摘要（name + description） | 稳定 | 7 |
| 5 | 核心能力 | `expertise.json` | 半稳定 | 3 |
| 6 | 工作风格 | `traits.json` | 半稳定 | 2 |
| 7 | 交付承诺 | `pipeline.json` | 半稳定 | 1（最先裁） |
| 8 | 用户上下文 | `context.md` | 动态（learner 会写） | 6 |
| 9 | 输出风格 | `agents/output_style.md`（全局共享） | 稳定 | 4 |
| 10 | 记忆 | 编译产物优先，raw 回退（见 5.3） | 动态 | 5 |
| 11 | 运行时上下文 | employee_id / name 等 dict | 每次不同 | **永不裁剪** |

> 代码注释称"11 层"（memory 与 runtime context 都标了 Layer 11），实际拼接 12 段。
>
> \* 裁剪顺序即 `cut_order = [7,6,5,9,10,8,4,3,1]`（`assembler.py:185`）——超出 token 预算（默认 100k，估算 ~3 字符/token）时**先砍锦上添花的结构化人格，最后才砍风格；身份、工作流、运行时上下文永不砍**。这个顺序本身就是设计声明：*角色是什么、必须怎么干活* 比 *它擅长什么* 更不可妥协。

### 5.2 稳定层缓存与 Prefix Cache

- 段 0–4（身份/风格/工作流/工具/技能）对同一 Agent 几乎不变 → 取 MD5 作为**稳定前缀 hash**（`assembler.py:163`）
- `PromptAssembler.get_prefix_cache_key()` 暴露该 hash；`LLMClient.chat(prefix_cache_key=...)` 通过 `extra_body.prefix_cache_key` 传给支持前缀缓存的推理服务（`llm/client.py:56`）
- 设计意图：把"稳定在前、动态在后"的分层顺序转化为真实的推理成本节省

### 5.3 记忆注入策略（两级回退）

```
优先：assemble_memory() 读编译产物 facts.md → longterm.md → week.md → today.md
回退：recent.jsonl 最近 10 条 + project/、agent/ 目录下最多 20 个条目摘要（每条截 150 字符）
```

编译产物是 LLM 蒸馏过的（每层 ≤400–600 字符），保证记忆段的 token 是**有界的**；raw 回退只在编译尚未发生时兜底。

---

## 六、执行引擎设计

### 6.1 分层执行模型总览

```
用户消息
   │
   ▼
┌──────────── 第一层：任务路由 task_router.py ────────────┐
│ [bugfix]/[feature]/[direct] 用户覆写 > 关键词计分 > LLM 兜底 │
└──────┬──────────────────────────┬───────────────────────┘
   DIRECT                    FEATURE / BUGFIX
       │                          │
       ▼                          ▼
  纯 ReAct 循环          ┌─ 第二层：技能链 DAG skill_chain.py ─┐
                        │  节点 = 技能 + 门禁 + 可选条件        │
                        │  每节点内部 ↓                        │
                        │  ┌─ 第三层：ReAct 循环 agent_loop.py ┐│
                        │  │  think → tool → observe（≤20 轮） ││
                        │  │  每次工具调用 ↓                   ││
                        │  │  ┌ 第四层：ToolGuard 安全拦截 ┐   ││
                        │  └──┴───────────────────────────┴───┘│
                        │  产出 → RubricGate → 节点 Gate        │
                        │  失败 → FailureLoopGuard → 重试/回退/阻断 │
                        └──────────────────────────────────────┘
```

### 6.2 任务路由（task_router.py）

三级决策，**优先级：用户覆写 > 关键词 > LLM 兜底**：

1. **覆写**：消息以 `[bugfix]` / `[feature]` / `[direct]` 开头 → 直接采纳并剥离标签（`_check_override`）
2. **关键词计分**：中英双语关键词各一组（bugfix 17 个、feature 16 个），分数高者胜，平手或零命中 → DIRECT
3. **LLM 兜底**（`route_task_with_llm`）：仅当关键词判 DIRECT 且传入了 llm 时，用一次分类调用复核

设计取舍：路由错误的代价不对称——DIRECT 误入技能链只是变慢，FEATURE 误判 DIRECT 会跳过质量流程。关键词表刻意宽泛（"修改""添加"都会命中），宁可多进链。

### 6.3 技能链 DAG（skill_chain.py）

**结构**：

```python
SkillNode(skill_name, gate, condition=None)   # condition(ctx) 返回 False 则跳过
SkillChain(nodes, backtrack_map)              # backtrack_map: 失败节点 → 回退目标
```

**预置链**（QoderWake 顺序）：

| 链 | 节点序列 | 回退边 |
|---|---|---|
| feature | planning → architecture（条件：计划涉及 ≥3 个文件） → testing-strategy → change-validation → code-review | change-validation→planning；code-review→change-validation；testing-strategy→planning |
| bugfix | sde-debug → planning → testing-strategy → change-validation → code-review | 同上 |
| refactor | planning → testing-strategy → change-validation → code-review | 同上 |

**配置即代码**：`SkillChain.from_workflow_md()`（`skill_chain.py:93`）能直接解析 Agent `workflow.md` 中的链定义：

```
### Feature 路由
    planning → architecture(仅大型变更) → testing-strategy → change-validation → code-review
```

- `→` 分隔的技能名映射到 `_GATE_MAP` 里的门禁（未知技能 → 默认 SkillRubricGate）
- 括号里含"仅/only/条件"→ 生成条件节点

这意味着**每个 Agent 可以在自己的 workflow.md 里声明专属技能链**，引擎读得懂——人格文件与执行引擎在这里闭环。

**回退边设计**：只允许"验证类节点退回生产类节点"（验证失败说明计划/实现有问题），不允许任意跳转——把回退空间限制成可推理的。

### 6.4 ReAct 微观循环（agent_loop.py）

一个循环三个变体，共享同一逻辑骨架：

| 变体 | 返回 | 用途 |
|---|---|---|
| `_react_loop`（:31） | `str` | 技能链节点内部、非流式 reply |
| `_react_stream_loop`（:103） | 文本 chunk 流 | 纯文字流式（终答改用 `chat_stream` 重发一次以获得逐字输出） |
| `_react_event_loop`（:161） | `ExecutionEvent` 流 | SSE 结构化事件（工具调用进度可见） |

骨架内的三个保护机制：

1. **滑动窗口**：对话超过 40 条 → 保留 system + 最近 30 条（防上下文爆炸）
2. **迭代上限**：默认 20 轮，超限返回 "Max ReAct iterations reached"
3. **连续失败自适应**：工具连续失败/被拦截 3 次 → 注入 system 提示"换方法：换工具、简化命令、或不用工具直接解释"，计数清零。**拦截不终止**——被 ToolGuard 挡下的调用以 `[BLOCKED] 原因` 作为工具观察值回给 LLM，让它自己绕路

### 6.5 门禁体系（gate.py，三级质量检查）

**统一接口**：`Gate.check(output, context) -> GateResult(verdict: pass|fail|retry, reason, retry_hint)`

每个技能链节点的产出要过两道检查，其中第二道可再叠加 LLM 复核：

```
产出 ──▶ ① SkillRubricGate（通用体检，所有节点共享）
              长度>50 且 含代码块/文件引用 且 无错误标记
        ──▶ ② 节点专属 Gate（规则正则）
              ──▶ ③ LLMGate（可选语义复核，仅 planning / change-validation）
```

**8 个节点门禁一览**：

| Gate | 绑定技能 | 检查什么（本质：要证据，不要口号） |
|---|---|---|
| PlanningGate | planning | ≥3 个编号步骤 + 含验证点关键词 |
| DesignGate | architecture | 涉及文件 + 数据流 + 依赖三要素 |
| TestGate | testing-strategy | ≥2 个测试用例 + 边界/异常覆盖 |
| ValidationGate | change-validation | 有执行痕迹 + 有具体 pass/fail 数字（不接受一句"passed"） |
| ReviewGate | code-review | 有严重度分级（P0/P1/P2）+ 有发现或明确"无问题" |
| RootCauseGate | sde-debug | 有根因陈述 + 有证据（日志/堆栈/输出） |
| TestDeliveryGate | （交付场景） | 测试真的跑了 + 有 pass/fail 计数 |
| GitWorktreeGate / PRGate | （git 场景） | 工作树干净无冲突 / 规范提交且无敏感文件入库 |

**LLMGate 的双层设计**（`gate.py:393`）：正则先跑（快、免费、抓形式）；正则 fail 直接返回；正则 pass 后才花一次 LLM 调用做语义复核（"这个计划是不是模板套话？"）。LLM 调用失败时静默信任正则——门禁永远不能因为自身故障阻塞执行。

**verdict 语义的实际处理**：主循环只区分 `pass` 与非 pass——`fail` 和 `retry` 都进入 FailureLoopGuard 裁决（`agent_loop.py:455-467`）。`retry_hint` 会作为下一次尝试的追加提示注入。

### 6.6 失败处理与回退

三层递进，全部是**代码裁决，不问 LLM**：

**第一层：Rubric 重试**（节点内，最多 3 次，`agent_loop.py:412`）
- 第 2 次尝试：注入上次的 `retry_hint`
- 第 3 次尝试：注入"换一种完全不同的策略"
- 3 次全败 → 直接 Blocked（产出连基本体检都过不了，不值得走回退）

**第二层：FailureLoopGuard**（跨节点状态机，`backtrack.py:13`）

失败签名 = `技能名 + 产出MD5前8位`。语义：**同样的地方摔同样的跤才算重复失败**。

```
record(sig) 裁决规则（max_same=2, max_strategies=2）：
  同一签名计数 < 2      → retry   （原地再试）
  已在 ≥2 个技能上失败过 → blocked （多点失败，停下来交给人）
  否则                  → switch  （按 backtrack_map 回退）
```

**第三层：回退护栏**
- `switch` 且该节点有回退边 → 跳回目标节点索引，全链回退次数 `max_backtracks=5` 封顶
- 无回退边或超限 → Blocked

**Blocked 的设计含义**：不是异常，是**正常出口**——框架承认"我搞不定"并带着最后的门禁原因停下，好过无限重试烧 token 或硬着头皮产出劣质结果。

### 6.7 断点恢复（session_state.py）

- 流式执行中，每个技能节点通过门禁后写一次 `SessionCheckpoint`（employee_id / session_id / task_type / 当前节点索引 / 累积 context）到 `sessions/.state/<sid>.json`（`agent_loop.py:311`）
- 链完成后清除；崩溃则文件残留，`restore()` / `list_active()` 可枚举待恢复会话
- session_id 有正则白名单 + resolve 校验，防路径穿越（`session_state.py:39`）

### 6.8 事件协议（events.py）

引擎与前端之间的流式契约——10 种 `EventType`，每种带自由 dict 负载，`to_sse()` 直接格式化为 SSE：

```
route_decided → skill_start → tool_call_start/tool_call_result …
→ gate_result → skill_end | backtrack | blocked → text_delta → done
```

设计点：**引擎产出结构化事件，翻译成什么样是上层的事**。`reply_stream` 把事件翻成文本标记（`[⚙ planning]`、`[门禁: pass]`、`[↩ 回退: …]`）供纯文本客户端；SSE 端点可以原样透传给富客户端渲染进度树。

---

## 七、记忆系统设计

设计目标：**越用越懂你，且注入 prompt 的 token 有界**。整体是一条"写入 → 编译 → 遗忘 → 注入/检索"的流水线。

### 7.1 记忆分层

```
              写入                    编译(LLM蒸馏)             注入
对话 ──▶ recent.jsonl(流水) ──┬──▶ today.md    (今日3-5事件,≤400字)──┐
     └─▶ agent|project/*.md   ├──▶ week.md     (7日主题,≤400字)     ├─▶ assemble_memory()
         (条目,带evidence)     ├──▶ longterm.md (滚动折叠,≤600字)    │    → prompt 第10段
                              └──▶ facts.md    (30日耐久事实,≤500字)─┘
         search.sqlite(FTS5+vec) ◀── 同步索引        ▲
                  │                                  │
                  └──▶ memory_ops 工具主动检索        └── Dream 整理(每5次对话)
```

### 7.2 写路径（store.py）

- **条目存储**：`FileMemoryStore`——每条记忆一个 md 文件（YAML frontmatter：id/scope/created_at/last_accessed；正文 + `Evidence:` 行）。scope 分 `project`（跨 Agent 共识）与 `agent`（个体经验），检索时 project 优先
- **对话落忆**（`save_conversation_memory`, `store.py:223`）：仅当本轮用过工具才落（纯闲聊不值得记）；同时 append 到 `recent.jsonl` 并写索引
- **为什么用文件不用库**：条目可人工审阅/编辑/删除——记忆是用户资产，透明度优先于查询性能；SQLite 只作为可重建的索引层

### 7.3 编译路径（compile.py，四层独立编译）

每层的套路一致：**取输入 → 算指纹（输入键 MD5）→ 指纹没变就跳过 → LLM 蒸馏 → 落盘 + 存指纹**。

蒸馏 prompt 的核心约束（`compile.py:69`）："只提取用户相关信息——是谁、关心什么、偏好、复现模式；**不要**文件名、工具调用、命令输出"。这一句决定了记忆的品质：记的是"关于用户的事实"，不是"执行日志"。

触发时机：非流式对话每 5 次（`_DREAM_INTERVAL`），先 Dream 清洗再编译——**先扔垃圾再蒸馏**，顺序不可反。

### 7.4 遗忘机制：Dream 整理（dream.py）

preview（生成计划）/ apply（执行）两段式，四个动作：

| 动作 | 规则 | 阈值 |
|---|---|---|
| 清秘 | 8 组正则（sk-、api_key=、ghp_、PRIVATE KEY…）命中即删 | — |
| 剪枝 | 超过 30 天且未再访问 → 删除 | `_PRUNE_DAYS=30` |
| 去重合并 | 关键词重叠 ≥70% 的条目合并（保最新，追加旧条目独有行） | `_OVERLAP_THRESHOLD=0.70` |
| 模式提取 | ≥3 条共享主题（重叠≥0.5）→ 生成一条 Pattern 汇总条目 | `_PATTERN_MIN_COUNT=3` |

设计立场：**遗忘是特性不是缺陷**——不清理的记忆库最终会让检索变差、prompt 变贵、秘密泄漏风险变高。

### 7.5 读路径与混合检索（search.py）

- **被动注入**：prompt 第 10 段（见 5.3），token 有界
- **主动检索**：LLM 通过 `memory_ops` 工具 search（Agent 自己决定什么时候"回忆"）
- **混合检索**：FTS5（BM25，永远可用）+ sqlite-vec（jina-embeddings-v3，1024 维，可选）→ **RRF 融合**（k=60）。降级链清晰：无向量扩展 → 纯 FTS5；索引整体异常 → 关键词全扫。任何一环失败都不影响主流程（全部 best-effort try/except）

### 7.6 偏好自学习（user_learner.py）

纯启发式（不花 LLM 调用），每轮对话观察用户消息：

- 4 个检测器：语言（zh/ja/en 字符频率）、详细度（词数 ≤10 / ≥80）、技术水平（40+ 术语命中 ≥2 → expert）、代码风格（type hints / functional / OOP…）
- **置信度门槛**：同一结论出现满 3 次才写入 `context.md`（`_CONFIDENCE_THRESHOLD=3`）
- **写入纪律**：只替换 `{{to_be_learned}}` 占位符或追加到 Preferences 段；**用户手写的值永不覆盖**——学习是填空，不是改答案

---

## 八、工具系统设计

### 8.1 Provider 约定：一个文件一个工具，零框架依赖

`agents/tools/*.py` 每个文件只需两个顶层符号：

```python
TOOL_META = {"name": ..., "description": ..., "parameters": {JSON Schema}}
async def execute(**kwargs) -> str: ...   # 同步函数也支持
```

`ToolRegistry.load_providers()`（`tool/registry.py:26`）用 `importlib` 逐文件加载注册。工具作者不 import 任何 engine 代码——**约定优于依赖**，这是"agents/ 零代码依赖"分层规则的落地。

### 8.2 内置工具清单

| 工具 | 职责 |
|---|---|
| `read_file` / `write_file` | 文件读写（受 FileGuard 目录白名单约束） |
| `shell` | 命令执行（受 dangerous_commands.json 规则拦截） |
| `git_ops` | Git 操作 |
| `web_fetch` | 网页抓取 |
| `memory_ops` | 记忆 CRUD（search/add/update/remove，与 FileMemoryStore 同格式互通） |
| `skill_load` | 按名加载 SKILL.md 全文（技能的运行时"翻书"） |
| `skill_manage` | 技能管理：list/get/create/edit/patch/versions/rollback（内置技能只读） |

### 8.3 执行保护

- 未知工具 / 抛异常 → 一律转成 `ToolResult(is_error=True)`，**工具失败永远不炸主循环**，作为观察值交还 LLM
- 输出超 4000 字符截断并标注总长（`tool/registry.py:88`）——保护上下文窗口
- `schema.py` 提供 `function_to_schema()`：从 Python 类型注解 + docstring 自动生成 OpenAI 工具 schema（Optional → 非必填，list[X] → array）

### 8.4 MCP 外接（tool/mcp_client.py）

- 自实现的**最小 MCP STDIO 客户端**（JSON-RPC 2.0，协议版 2024-11-05）：initialize 握手 → tools/list 发现 → tools/call 调用
- 发现的工具统一加 `mcp_` 前缀注册进同一个 ToolRegistry——对 ReAct 循环而言 MCP 工具与本地工具**无差别**
- 来源：Agent `config.yaml` 的 `mcp_servers: [{command, env}]`；连接失败静默跳过（best-effort），单次响应读超时 30s，关闭超时 5s 后 kill

---

## 九、技能系统设计

### 9.1 技能 vs 工具 vs 插件

| | 本质 | 形态 | 谁执行 |
|---|---|---|---|
| 工具 | 原子能力（"能做什么"） | Python 函数 | 代码执行，结果回给 LLM |
| 技能 | 方法论（"该怎么做"） | SKILL.md 文档 | LLM 读着它执行（注入 prompt 的 ReAct） |
| 插件 | 事件源 + 响应（"何时被唤起"） | manifest + handler.py | 触发器调 handler，handler 可再调引擎 |

### 9.2 SKILL.md 规范

YAML frontmatter（name/description/version/argument_hint，兼容 trigger/input/output 等扩展字段）+ Markdown 正文（Goal / Process / 分步指引）。与 Claude Code 的 SKILL.md 生态同构，技能可直接互相搬运。

### 9.3 双源加载与版本化

- **内置技能**（`agents/skills/`，7 个：planning / architecture / testing-strategy / change-validation / code-review / sde-debug / project-analysis）：只读，Git 管理，是技能链的节点素材
- **Agent 自装技能**（`employees/<id>/skills/`）：同名可覆盖内置（registry 后加载者胜）；可通过 `skill_manage` 工具由 Agent **自己创建和修改**
- **版本控制**（`skill/store.py`）：每次修改前把旧版存入 `.versions/`（保留最近 10 个快照），支持 rollback——Agent 自改技能是高风险操作，可回滚是启用它的前提

### 9.4 执行模型（skill/executor.py）

```
execute_skill(): SKILL.md 全文 + 链上下文 ──作为独立 system prompt──▶ 新开一个 ReAct 循环
```

关键设计：技能执行**不复用**Agent 的 12 段大 prompt，而是用"纯技能视角"的小上下文——让每个链节点专注单一方法论，前序节点产出通过 `context` dict（`{skill}_output`）显式传递，而不是靠共享一条越来越长的对话。rubric 重试的反馈也经由 `context["rubric_feedback"]` 注入。

---

## 十、插件系统设计

### 10.1 Manifest 规范（plugin.json）

```json
{
  "schema": "agentsmith.plugin.v1",
  "name": "github", "version": "0.1.0",
  "description": "...",
  "trigger_type": "polling | webhook | manual",
  "polling_interval_seconds": 60,
  "skills": [ ... ]
}
```

### 10.2 三种触发器（plugin/trigger.py）

| 触发器 | 模型 | 说明 |
|---|---|---|
| PollingTrigger | 常驻 asyncio task，间隔 `poll()` | 轮询外部源（如 GitHub issues）；单事件 handler 异常不打断循环 |
| WebhookTrigger | 无后台任务，HTTP 路由推事件进来 | `handle_event(payload)` 返回 accepted/error |
| CronTrigger | 常驻 task，解析 `M H * * *` 简化 cron | 定时任务（如 daily-report） |

### 10.3 Handler 约定

`handler.py` 暴露 `async def handle(event: dict)`，与工具 provider 同样的**约定式加载**（`plugin/loader.py`）。发现（PluginRegistry.discover 扫 plugin.json）、加载、触发全部 best-effort，坏插件只影响自己。

---

## 十一、安全设计

分层防御，每层独立生效：

| 层 | 机制 | 实现 |
|---|---|---|
| L1 规则拦截 | 工具调用前正则匹配危险模式 | `ToolGuard` + `agents/safety/dangerous_commands.json` |
| L2 文件边界 | 路径白名单 + 敏感目录黑名单 | `FileGuard`（tool_guard.py:17） |
| L3 质量门禁 | 产出必须带真实证据，防"谎报成功" | Gate 体系（6.5） |
| L4 提交防线 | 敏感文件（.env/credentials/密钥）禁止入库 | `PRGate`（gate.py:327） |
| L5 记忆消毒 | 已落库的秘密被周期清除 | Dream 清秘（7.4） |

**L1 规则格式**（安全规则也是内容，不是代码）：

```json
{
  "id": "cmd-inj-001", "tools": ["shell"], "severity": "critical",
  "patterns": ["\\|\\s*(bash|sh|zsh)"],
  "excludePatterns": ["\\|\\s*grep", "\\|\\s*head"],
  "description": "...", "remediation": "..."
}
```

覆盖类别：命令注入、fork 炸弹/死循环/巨型文件（资源滥用）、inline eval/exec（代码执行）、rm -rf / DROP TABLE / git --force / dd 等破坏性命令。`tools` 字段限定规则作用域；`excludePatterns` 用白名单精修误报（如允许 `| grep`）。

**L2 语义**：默认允许 `$HOME`、`/tmp`、cwd；但 `.ssh/.gnupg/.aws/.kube` **在白名单内也一律拒绝**。shell 命令中的绝对路径会被正则提取后逐一过检。

**统一处置哲学**：拦截 ≠ 终止。所有拦截以 `[BLOCKED] 原因` 作为工具观察返回，LLM 得知边界后自行调整方案；连续 3 次受阻才触发"换方法"提示（6.4）。

---

## 十二、配置体系

五级合并（`common/config_loader.py:29`），**下层覆盖上层已有字段，未填字段继承**：

```
env（AGENTSMITH_LLM_*，最低）
  < 平台 ~/.agent-smith/config.yaml
    < 模板 agents/templates/<role>/config.yaml
      < Agent employees/<id>/config.yaml
        < 会话 session_override dict（最高）
```

合并语义（`merge_configs`）：深合并；**值为 None 视为"未设置"跳过**——所以模板里 `model: null` 表达"继承平台配置"而不是"清空"。产出统一的 LLM 配置（api_key/base_url/model/provider/stream/embedding_model），engine 只认 OpenAI-compatible 端点（`llm/client.py`：重试 3 次、超时 300s、支持 prefix_cache_key）。

---

## 十三、服务端集成契约

engine 对上只暴露两个入口（server 不触碰引擎内部）：

```python
# engine/execution/agent_loop.py
async def reply(employee_id, name, user_message) -> str                       # :496
async def reply_stream(employee_id, name, user_message) -> AsyncGenerator[str] # :581
```

`SessionService`（server/app/services/session_service.py）的职责边界：会话存在性校验 → 用户消息落库 → 调 engine → 助手消息落库 → SSE 组帧（`event: message` 逐块 + `event: done` 收尾）。**server 不知道技能链、门禁、记忆的存在**——它们全部封装在这两个函数之后。

---

## 十四、设计权衡与已知局限

诚实清单（均为当前代码事实，非猜测）：

### 14.1 有意的取舍

| 取舍 | 理由 |
|---|---|
| 正则门禁而非全 LLM 评审 | 快、免费、可解释；语义漏洞由 LLMGate 兜（仅 2 个关键节点付 LLM 成本） |
| 关键词路由而非全 LLM 路由 | 路由是高频操作；`route_task_with_llm` 已实现 LLM 兜底但主入口暂未启用 |
| 文件存储而非数据库 | 人格/记忆/技能都是用户可审阅资产；SQLite 只做可重建索引 |
| 每次请求重建 Registry/连 MCP | 实现简单、无状态残留；代价是 MCP 冷启动延迟（演进方向：常驻连接池） |
| 单一 OpenAI-compatible LLM 客户端 | 国产/自建推理端点全兼容此协议；多 provider 抽象是伪需求（YAGNI） |

### 14.2 已知不对称与待办

1. **Checkpoint 只在流式链路写**：`run_agent_stream` 每节点存档，`run_agent` 不存
2. **门禁把 `fail` 与 `retry` 同等处理**：verdict 三值设计，但主循环只二分 pass / 非 pass
3. **CronTrigger 是简化 cron**：只支持 `M H * * *` 的时分字段
4. **向量检索依赖 LLM base_url 提供 `/embeddings`**：常见推理端点（如 GLM）不带 jina embedding，向量路会静默降级为纯 FTS5
5. **`project` scope 无自动写入口**：`save_conversation_memory` 固定 `scope="agent"`，跨 Agent 共识层只能靠 `memory_ops` 手动写

已修复（2026-07-05）：

- ~~流式路径不落对话记忆~~ → `reply_stream()` 现按事件流跟踪工具使用并调用 `save_conversation_memory`（顺带修正了非真实的 `had_tools=True`）
- ~~记忆混合检索未接入 prompt 注入~~ → 新增 `search_relevant_memories()`（`memory/store.py`），`reply`/`reply_stream` 组装 prompt 前按用户消息做 query-time 混合检索 top-5，经 `assemble(retrieved_memory=...)` 注入记忆段
- ~~会话历史未进 ReAct 上下文~~ → `SessionService` 取最近 10 条消息经 `history` 参数传入 `reply`/`reply_stream`，拼进 base_messages

### 14.3 演进方向

- Checkpoint 打平到非流式链路
- 路由主入口切换到 `route_task_with_llm`
- Registry/MCP 连接常驻化（进程级缓存）
- 独立 embedding 端点配置（与 LLM base_url 解耦），让向量检索真实生效
- 门禁 verdict 三态语义完整化（fail 直接 Blocked、retry 走 guard）

---

## 附录：文件地图

| 子系统 | 文件 | 行数 | 职责 |
|---|---|---|---|
| 执行 | `engine/execution/agent_loop.py` | 660 | ReAct 三变体 + 链执行 + reply/reply_stream 入口 |
| 执行 | `engine/execution/skill_chain.py` | 150 | SkillNode/SkillChain、预置链、workflow.md 解析 |
| 执行 | `engine/execution/gate.py` | 498 | 8 规则门禁 + SkillRubricGate + LLMGate |
| 执行 | `engine/execution/task_router.py` | 71 | 覆写/关键词/LLM 三级路由 |
| 执行 | `engine/execution/backtrack.py` | 37 | FailureLoopGuard 状态机 |
| 执行 | `engine/execution/session_state.py` | 76 | SessionCheckpoint 断点存取 |
| 执行 | `engine/execution/events.py` | 51 | 10 种 ExecutionEvent + SSE 序列化 |
| Prompt | `engine/prompt/assembler.py` | 256 | 12 段组装、token 裁剪、稳定层 hash |
| Prompt | `engine/prompt/placeholder.py` | 15 | `{{key}}` 渲染 |
| 记忆 | `engine/memory/store.py` | 307 | FileMemoryStore + 对话落忆 + Dream/编译调度 |
| 记忆 | `engine/memory/compile.py` | 223 | 四层编译 + 指纹缓存 + assemble_memory |
| 记忆 | `engine/memory/search.py` | 188 | FTS5 + sqlite-vec + RRF 混合检索 |
| 记忆 | `engine/memory/dream.py` | 240 | 去重/剪枝/模式提取/清秘 |
| 记忆 | `engine/memory/user_learner.py` | 229 | 偏好检测 + 置信度写入 context.md |
| LLM | `engine/llm/client.py` | 124 | OpenAI-compatible 客户端（重试/流式/prefix cache） |
| 工具 | `engine/tool/registry.py` | 97 | provider 加载、schema、执行与截断 |
| 工具 | `engine/tool/mcp_client.py` | 151 | MCP STDIO 客户端与注册 |
| 技能 | `engine/skill/{loader,registry,executor,store}.py` | 326 | SKILL.md 解析/双源注册/注入执行/版本化 |
| 插件 | `engine/plugin/{registry,trigger,loader}.py` | 286 | manifest 发现/三种触发器/handler 加载 |
| 安全 | `engine/safety/tool_guard.py` | 121 | ToolGuard + FileGuard |
| 内容 | `agents/templates/` × 8 角色 | — | 9 文件人格模板 |
| 内容 | `agents/skills/` × 7 | — | 内置技能 |
| 内容 | `agents/tools/` × 8 | — | 工具 provider |
| 内容 | `agents/safety/dangerous_commands.json` | — | L1 安全规则 |
| 配置 | `common/config_loader.py` | 76 | 五级配置合并 |
