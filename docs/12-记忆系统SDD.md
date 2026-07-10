# 12 · Agent 记忆系统设计文档（SDD）

## 0. 文档控制

| 项 | 内容 |
|---|---|
| 文档类型 | Software Design Document（软件设计规格书） |
| 版本 | v1.1 |
| 状态 | **已验收**——独立 Agent 判定 PASS-WITH-CORRECTIONS，全部修正已落实（见第 14 章验收记录） |
| 覆盖范围 | `engine/memory/`（store / compile / dream / search / user_learner / interface）+ 注入点 `engine/prompt/assembler.py` + 入口接线 `engine/execution/agent_loop.py` + Agent 侧工具 `agents/tools/memory_ops.py` |
| 代码基线 | 2026-07-05（含 query-time 检索注入 / 流式落忆 / 会话历史三项修复） |
| 读者 | 引擎开发者、评审 Agent、面试官 |

**验收方式**：本文档第 11 章给出可测试的验收标准（AC-1 ~ AC-9）；验收 Agent 须逐条对照代码与运行行为核实第 4–8 章的全部技术断言，产出结构化验收报告。

---

## 1. 引言

### 1.1 目的

定义 Smith 这个单常驻 Agent 的记忆子系统：它要解决什么问题、如何设计、**为什么这样设计而不是别的方案**、做了哪些取舍、参考了哪些已有设计。

目录心智以 `docs/13-单常驻Agent架构重梳理.md` 为准：目标记忆目录是 `~/.agent-smith/agent/memory/`。代码参数已命名为 `agent_dir`；磁盘上的 `employees/<id>` 仍是迁移期兼容路径，不再代表“数字员工”产品模型。

### 1.2 问题陈述

LLM 是无状态的。一个"Agent"如果每次对话都从零开始，它就只是一个带角色扮演提示词的聊天框。要成为"Agent"，必须满足：

1. **记得住**——跨会话保留与用户和项目相关的事实
2. **想得起**——在当前任务需要时，把相关的旧经验带进上下文
3. **忘得掉**——过时、重复、危险（含密钥）的记忆必须消亡，否则记忆库随时间必然腐化
4. **学得会**——从交互中沉淀用户偏好，而不需要用户显式配置
5. **不添乱**——记忆的任何环节故障都不能阻塞对话主流程；注入 prompt 的记忆 token 必须有界

### 1.3 术语

| 术语 | 定义 |
|---|---|
| 记忆条目（Entry） | 一条独立记忆，一个带 YAML frontmatter 的 .md 文件 |
| 流水（recent.jsonl） | 按时间追加的原始对话摘要日志 |
| 编译（Compile） | 用 LLM 把流水蒸馏成分层摘要（today/week/longterm/facts） |
| Dream | 周期性记忆整理：去重、剪枝、模式提取、清秘 |
| 被动注入 | 组装 system prompt 时自动带入的记忆 |
| 主动检索 | LLM 通过 `memory_ops` 工具自主发起的记忆查询 |
| scope | 记忆作用域：`agent`（个体经验）/ `project`（跨 Agent 共识） |

---

## 2. 需求与约束

### 2.1 功能需求

| ID | 需求 |
|---|---|
| FR-1 | 使用过工具的对话结束后自动持久化一条对话记忆（纯闲聊不落） |
| FR-2 | 记忆分 agent / project 双作用域，project 检索优先 |
| FR-3 | 周期性把流水编译为四层摘要：today / week / longterm / facts |
| FR-4 | 周期性整理：≥70% 重叠去重、30 天未访问剪枝、≥3 条同主题聚合、密钥清除 |
| FR-5 | 组 prompt 时注入编译摘要；并按当前用户消息做 query-time 相关性检索注入 top-k |
| FR-6 | 提供混合检索：FTS5 全文 + 向量语义 + RRF 融合，逐级降级 |
| FR-7 | LLM 可通过工具对记忆做 search / add / update / remove |
| FR-8 | 从对话自动学习用户偏好（语言/详细度/技术水平/代码风格）写入 context.md |

### 2.2 非功能约束

| ID | 约束 | 落地 |
|---|---|---|
| NFR-1 | **best-effort**：记忆链路任何失败不得阻塞对话 | 全链路 try/except 静默降级 |
| NFR-2 | **token 有界**：被动注入的记忆量必须有上限 | 编译层 400–600 字符限幅（提示词软约束，代码不硬截断）；检索 top-5、单条 200 字符（代码硬截断） |
| NFR-3 | **零部署**：不引入需要独立部署的存储/检索服务 | 文件 + 内嵌 SQLite（FTS5 / sqlite-vec） |
| NFR-4 | **用户可审计**：记忆是用户资产，可人工查看/编辑/删除 | 每条记忆一个明文 .md 文件 |
| NFR-5 | **成本可控**：编译等 LLM 调用不得随对话次数线性增长 | 指纹缓存 + 每 5 次对话才触发 |
| NFR-6 | **隐私**：密钥类内容不得长期驻留记忆 | Dream 清秘（8 组正则）+ memory_ops 写入前敏感检查 |

---

## 3. 总体设计

### 3.1 架构：一条"写入 → 编译 → 遗忘 → 注入/检索"的流水线

```
                写入                     编译(LLM蒸馏+指纹缓存)          注入
对话结束 ──▶ recent.jsonl(流水) ──┬──▶ today.md    (今日3-5事件)  ──┐
   (had_tools 门槛)              ├──▶ week.md     (7日主题)      ├─▶ assemble_memory()
        └──▶ agent|project/*.md  ├──▶ longterm.md (滚动折叠)     │    → prompt 记忆段
             (条目+Evidence)      └──▶ facts.md    (30日耐久事实) ─┘         ▲
                  │                          ▲                              │
                  ▼                          │ (每5次对话,先清洗后编译)      │
        search.sqlite(FTS5+vec) ◀── 同步索引  │                              │
                  │                    Dream(去重/剪枝/模式/清秘)             │
                  ├──▶ query-time 检索 top-5 ────────────────────────────────┘
                  └──▶ memory_ops 工具主动检索
```

### 3.2 分层对应（设计隐喻：人类记忆模型）

整体分层参考 Atkinson–Shiffrin 三级记忆模型：

| 人类记忆 | 本系统 | 特征 |
|---|---|---|
| 感觉登记 | `recent.jsonl` 流水 | 原始、全量、无加工 |
| 短时记忆 | `today.md` / `week.md` | 时效性强、周期重编译 |
| 长时记忆 | `longterm.md` / `facts.md` / 记忆条目 | 蒸馏后的耐久事实，经"睡眠"（Dream）巩固 |

Dream 的命名与机制参考 Stanford Generative Agents（Park et al., 2023）的 **reflection** 环节：原始观察积累到一定量后，离线归纳出更高层的抽象（本系统的"模式提取"）；同时承担人脑睡眠期间的突触修剪职能（去重与剪枝）。

### 3.3 模块与文件

| 模块 | 文件 | 职责 |
|---|---|---|
| 条目存储 | `engine/memory/store.py` → `FileMemoryStore` | 条目 CRUD、scope 目录、frontmatter 解析 |
| 对话落忆 | `store.py` → `save_conversation_memory()` | 写流水+条目+索引，调度 Dream/编译 |
| query-time 检索 | `store.py` → `search_relevant_memories()` | 按用户消息混合检索 top-k，格式化为注入块 |
| 编译 | `engine/memory/compile.py` | 四层编译 + 指纹缓存 + `assemble_memory()` |
| 遗忘 | `engine/memory/dream.py` → `DreamConsolidator` | preview/apply 两段式整理 |
| 混合检索 | `engine/memory/search.py` → `SearchIndex` | FTS5 + sqlite-vec + RRF |
| 偏好学习 | `engine/memory/user_learner.py` | 4 检测器 + 置信度写 context.md |
| 注入点 | `engine/prompt/assembler.py`（记忆段 + `retrieved_memory` 参数） | 编译摘要 + 检索块合并注入 |
| Agent 侧工具 | `agents/tools/memory_ops.py` | LLM 主动记忆 CRUD（与 FileMemoryStore 同格式） |
| 接口协议 | `engine/memory/interface.py` | `MemoryEntry` 数据类 + `MemoryStore` Protocol |

---

## 4. 详细设计

### 4.1 写路径

**触发**：`reply()` 与 `reply_stream()` 在对话收尾时调用 `save_conversation_memory(agent_dir, user_msg, reply, had_tools)`。流式路径通过执行事件流（`TOOL_CALL_START` / `SKILL_START`）跟踪 `had_tools`。

**门槛**：`had_tools=False` 直接返回——只有"干过活"的对话才值得记（FR-1）。设计判断：闲聊记忆是纯噪音，它会稀释检索质量并抬高编译成本。

**写入内容**（两份，用途不同）：
1. `recent.jsonl` 追加一行 `{"task": user_msg[:100], "summary": reply[:200], "timestamp": ISO-8601}` ——作为编译的**原料**
2. `FileMemoryStore.add()` 写一个条目 .md ——作为检索的**对象**，并同步写入 search.sqlite 索引

**条目文件格式**：

```markdown
# 目标位置：~/.agent-smith/agent/memory/agent/<id>.md
# 当前兼容位置：~/.agent-smith/employees/<id>/memory/agent/<id>.md
---
id: a1b2c3d4e5f6
scope: agent
created_at: 2026-07-05T10:00:00+00:00
last_accessed: 2026-07-05T10:00:00+00:00
---
Task: 修复登录接口的 500
Result: 根因是空指针，已加防御 + 单测

Evidence: conversation at 2026-07-05T10:00:00+00:00
```

`Evidence` 是一等公民字段：每条记忆必须能回答"你凭什么记得这个"——与门禁系统"要证据不要口号"的哲学同源。

**调度**：写入后递增 `.dream_counter`，满 5 次（`_DREAM_INTERVAL`）归零并依次执行 Dream → 四层编译。**顺序不可反**：先清洗（扔掉重复/过期/密钥）再蒸馏，否则垃圾会被编译进摘要。

### 4.2 编译路径（compile.py）

四层独立编译，共享同一套路：**取输入 → 指纹（输入键列表的 MD5）→ 指纹未变则跳过 → 一次 LLM 蒸馏 → 落盘 + 存指纹**。

| 层 | 输入 | 输出约束（提示词软约束，各层在任务指令中声明） | 累积方式 |
|---|---|---|---|
| `compile_today` | 今日流水 | 3–5 个关键事件，≤400 字符 | 每日重建 |
| `compile_week` | 7 日流水 | 3–5 个复现主题，≤400 字符 | 滚动窗口重建 |
| `compile_longterm` | week.md | ≤600 字符 | **折叠式**：新周摘要 merge 进既有长期记忆，LLM 负责去重 |
| `compile_facts` | 30 日流水（最多 50 条） | ≤500 字符 | **携带式**：上版事实作为输入，仍有效的事实被"carry forward" |

**蒸馏 prompt 的核心约束**（所有层共享 system prompt）：

> "只提取用户相关信息：用户是谁、关心什么、偏好、复现模式。**不要**文件名、工具调用、命令输出、执行细节。"

这一句是整个记忆系统品质的支点——它把记忆定义为"**关于用户的事实**"而不是"执行日志"。没有它，记忆库会被 `ls -la 的输出` 这类内容填满。

**指纹缓存的意义**（NFR-5）：编译是 LLM 调用（花钱、有延迟）。输入不变时重编译是纯浪费——指纹把编译成本从 O(对话次数) 降为 O(内容变化次数)。

### 4.3 遗忘机制：Dream（dream.py）

**两段式**：`preview()` 只读分析生成 `_DreamPlan`（secret_ids / prune_ids / merges / pattern_summaries），`apply()` 执行。分离的理由：整理是破坏性操作，计划必须先于执行可被检视（未来可加人工确认门）。

四个动作按序执行：

| 动作 | 算法 | 阈值 | 设计依据 |
|---|---|---|---|
| 清秘 | 8 组正则（`sk-…`、`api_key=`、`ghp_…`、`PRIVATE KEY` 等）命中即删 | — | NFR-6：密钥进了记忆 = 每次注入 prompt 都在泄漏 |
| 剪枝 | `last_accessed` 距今 > 30 天 → 删 | `_PRUNE_DAYS=30` | 艾宾浩斯遗忘曲线的工程化：不再被访问的记忆价值指数衰减 |
| 去重合并 | 关键词集合重叠率 ≥0.70 的条目分组；保最新条目，追加旧条目独有行 | `_OVERLAP_THRESHOLD=0.70` | 重复记忆使检索结果同质化 |
| 模式提取 | 重叠 ≥0.5 的条目聚簇；簇大小 ≥3 生成一条 `Pattern (N entries): 共享关键词` 汇总 | `_PATTERN_MIN_COUNT=3` | Generative Agents 的 reflection：多次观察 → 一条抽象 |

关键词重叠算法：`|A∩B| / min(|A|,|B|)`，关键词 = 3+ 字符的中英文词。复杂度 O(n²)——这是**有意接受的天花板**（详见 DR-08），当前单 Agent 条目量级（百级）下毫秒完成。

### 4.4 混合检索（search.py）

**索引结构**（`search.sqlite`，每 Agent 一个，WAL 模式）：
- `memory_fts`：FTS5 虚拟表（`entry_id, content, scope`，unicode61 分词）——**永远可用**（FTS5 内建于 SQLite）
- `memory_vec`：sqlite-vec 虚拟表（`entry_id, embedding float[1024]`）——**可选**（依赖 sqlite-vec 扩展 + embedding 端点）

**检索流程**：

```
query ──┬─▶ FTS5 BM25 取 2k 条
        └─▶ 向量 L2 距离 取 2k 条（sqlite-vec 默认度量；归一化 embedding 下与余弦排序等价）
              │
              ▼
        RRF 融合: score(d) = Σ 1/(60 + rank_i(d))  → top-k
```

**降级链**（NFR-1 的检索侧落地）：

```
向量+FTS5+RRF → （无向量）纯 FTS5 → （FTS5 语法错/索引空）关键词全文件扫描 → （全部失败）返回空
```

每级降级都静默发生，主流程无感知。

**RRF 参数**：k=60，取自 Cormack, Clarke & Büttcher (2009) 的推荐默认值。选 RRF 而非加权分数融合的理由见 DR-06。

**Embedding**：OpenAI-compatible `/embeddings` 端点 + `jina-embeddings-v3`（1024 维），通过 `create_jina_embed_fn()` 构造。已知局限：端点复用 LLM 的 `base_url`（见第 12 章）。

### 4.5 读路径：被动注入 + 主动检索双轨

**轨道 A：被动注入**（每次组 prompt 必然发生，token 有界）

prompt 记忆段 = 编译摘要 + query-time 检索块：

1. `assemble_memory()`：按 facts → longterm → week → today 顺序拼接编译产物（总量有界：4 层 × ≤600 字符）；无编译产物时回退到 raw（recent.jsonl 末 10 条 + 条目摘要 ≤20 条 × 150 字符）
2. `search_relevant_memories(agent_dir, user_message, top_k=5)`：按**当前用户消息**做混合检索，格式化为 `## Relevant Memories` 块（单条截 200 字符），经 `assemble(retrieved_memory=...)` 追加到记忆段。参数 `agent_dir` 语义上即 Smith 的 profile dir。

两者互补：编译摘要回答"这个用户总体是谁"（**画像**），检索块回答"和这句话有关的旧经验是什么"（**情景**）。只有摘要则记忆与任务无关，只有检索则丢失全局画像——双轨是刻意的（DR-03）。

**轨道 B：主动检索**（LLM 自主决策）

`memory_ops` 工具暴露 search/add/update/remove。Agent 在 ReAct 循环中自己判断"这个问题我是不是记过什么"，这对应人类的**主动回忆**行为。工具与 `FileMemoryStore` 读写**相同的文件格式与目录布局**（scope 子目录 + `last_accessed` 字段；根目录旧条目兼容读取，update 时自动迁移进子目录）——Agent 写的记忆，组装器与检索看得见；反之亦然（单一事实源）。残余差异：工具写入暂不进 search.sqlite 索引，在索引有其他命中时可能不出现在 query-time 检索结果中（关键词回退路径可见，见 §12）。

**注入与裁剪的关系**：记忆段在 prompt 组装器的裁剪优先级中排第 5（先于身份/工作流被裁）——记忆是增强，不是身份的一部分；预算不足时宁可失忆，不可失格。

### 4.6 偏好自学习（user_learner.py）

**纯启发式，零 LLM 调用**。每轮对话观察用户消息：

| 检测器 | 信号 | 输出 |
|---|---|---|
| 语言 | 中/日/英字符频率 | zh / ja / en |
| 详细度 | 词数 ≤10 → concise；≥80 → detailed | 沟通风格 |
| 技术水平 | 36 个术语命中 ≥2 | expert |
| 代码风格 | type hints / functional / OOP / dataclass / pydantic / async 等模式 | 风格标签 |

**置信度门槛**：同一结论累计观察满 3 次（`.learner_state.json` 计数）才写入 `context.md`。单次信号可能是偶然（一句英文不代表用户偏好英文），三次是"模式"。

**写入纪律**（防越权，按序尝试）：
1. 只替换 `{{to_be_learned}}` 占位符
2. 字段已有真实值 → **放弃写入**（用户手写内容神圣不可侵犯）
3. 字段不存在但有 Preferences 段 → 追加

学习是**填空，不是改答案**。

### 4.7 会话短期上下文（边界说明）

最近 10 条会话消息由 `SessionService` 直接从消息表读取、经 `history` 参数注入 ReAct 上下文。**这不属于记忆系统**——"上一句说了什么"是会话状态，不该由异步蒸馏的记忆层承担。明确这条边界，记忆层才能专注做"跨会话的经验"而不被当成聊天缓存使用。

---

## 5. 数据设计

| 文件 | 格式 | 字段 | 生产者 → 消费者 |
|---|---|---|---|
| `memory/recent.jsonl` | JSONL | `task`(≤100字) / `summary`(≤200字) / `timestamp`(ISO-8601 UTC) | save_conversation_memory → compile |
| `memory/agent/*.md`、`memory/project/*.md` | frontmatter + 正文 + Evidence | `id`(12位hex) / `scope` / `created_at` / `last_accessed` | store & memory_ops → 检索/Dream |
| `memory/{today,week,longterm,facts}.md` | Markdown | `## 标题` + 蒸馏正文 | compile → assemble_memory |
| `memory/.fp_{today,week,longterm,facts}` | 纯文本 MD5 | 指纹 | compile（自产自销） |
| `memory/.dream_counter` | 纯文本整数 | 计数 | save_conversation_memory（自产自销） |
| `memory/search.sqlite` | SQLite（FTS5 + vec0 虚拟表） | 见 4.4 | store 索引 → SearchIndex |
| `.learner_state.json` | JSON | `counters.{key}.{value}` 计数、`written` | user_learner（自产自销） |

**一致性原则**：.md 文件是**唯一事实源**，search.sqlite 是**可丢弃的派生索引**（删了可重建，不影响正确性，只影响检索质量降级为扫描）。

---

## 6. 接口设计

```python
# 协议（engine/memory/interface.py）
@dataclass
class MemoryEntry:
    id: str; content: str; scope: Literal["agent","project"]
    evidence: str; created_at: str; last_accessed: str = ""

class MemoryStore(Protocol):
    async def search(self, query) -> list[MemoryEntry]
    async def add(self, content, evidence, scope) -> MemoryEntry
    async def update(self, entry_id, content=None, evidence=None) -> bool
    async def remove(self, entry_id) -> bool

# 引擎内部关键入口
save_conversation_memory(agent_dir, user_msg, reply, had_tools) -> None         # 写路径总入口
search_relevant_memories(agent_dir, query, top_k=5) -> str                      # query-time 注入块
assemble_memory(memory_dir) -> str                                              # 编译摘要拼接
run_compilation(memory_dir, llm) -> dict                                        # 四层编译
DreamConsolidator(store).preview() / .apply()                                   # 整理
UserPreferenceLearner(agent_dir).observe(user_msg, reply) -> list[str]          # 偏好学习
SearchIndex(memory_dir).open(embed_fn) / .index_entry() / .search() / .close()  # 索引
```

失败语义分两级（合起来落实 NFR-1）：**读路径入口**（`search_relevant_memories`）自吞异常返回空串；**写路径**（`save_conversation_memory` / `run_compilation` / Dream）可能向上抛出，由调用方兜底——`reply()` 与 `reply_stream()` 对落忆与偏好学习均有 best-effort 包裹，异常不影响对话返回。

---

## 7. 设计决策记录（为什么是这样，而不是别的）

> 每条 DR：背景 → 候选方案 → 决策 → 理由 → 接受的代价。

### DR-01 存储主体：明文文件，而非数据库/向量库

- **候选**：(a) 全量 SQLite；(b) 专用向量库（Chroma/Qdrant/Milvus）；(c) 明文 .md 文件 + SQLite 派生索引
- **决策**：(c)
- **理由**：记忆是**用户资产**——本地 Agent 的记忆必须让用户能打开看、能改、能删（NFR-4）。明文文件天然可审计、可 Git、可迁移；(a) 对用户是黑盒；(b) 还引入独立部署（违反 NFR-3），且百级条目量远撑不满向量库的设计容量。参考 Claude Code 的 memory 目录形态（每条记忆一个 md 文件 + 索引文件）。
- **代价**：文件 I/O 无事务；并发写同一 Agent 记忆可能竞态（单用户桌面产品，接受）；检索必须靠派生索引补偿。

### DR-02 压缩策略：时间分层编译，而非 MemGPT 分页 / 单一滚动摘要 / 不压缩纯 RAG

- **候选**：(a) MemGPT 式虚拟内存分页（LLM 自主 page in/out）；(b) 单一滚动摘要（每次对话后重写一份总摘要）；(c) 不压缩，全量入库纯靠检索；(d) 时间分层四级编译
- **决策**：(d)
- **理由**：(a) 让 LLM 管理自己的内存需要额外的函数调用轮次和强指令遵循，在中小模型上不可靠，且调试困难；(b) 单一摘要每次全量重写——高频信息反复冲刷低频但重要的事实（"用户上周说的部署偏好"会被"今天调了三次 CSS"挤掉），且无法区分时效性；(c) 纯 RAG 检索回答不了"这个用户总体是谁"这种无明确 query 的画像问题，而画像恰恰是每次对话都需要的。时间分层（today/week/longterm/facts）让不同时效的信息各有归宿：新信息进短层，经得起时间的信息才折叠进长层——这是对人类记忆巩固（consolidation）过程的直接工程模仿。ChatGPT Memory 的"从对话提取耐久用户事实"对应本设计的 facts 层。
- **代价**：四层各一次 LLM 调用（指纹缓存 + 每 5 次触发缓解）；蒸馏有损，细节回溯要靠条目检索兜底。

### DR-03 注入策略：画像摘要 + query-time 检索双轨，而非单轨

- **候选**：(a) 只注入编译摘要；(b) 只做 query-time RAG top-k；(c) 双轨
- **决策**：(c)
- **理由**：两轨回答的是不同问题。(a) 的缺陷在修复前的系统里已被实证：记忆与当前任务无关，检索索引白建；(b) 的缺陷是 query 驱动——用户说"继续"时检索不到任何东西，画像信息（语言偏好、技术水平）也不该依赖 query 命中。双轨成本可控：摘要受提示词限幅（约 2k 字符量级，软约束），检索 top-5 × 200 字符为代码硬截断（NFR-2）。
- **代价**：每次组 prompt 多一次索引查询（毫秒级）+ 可能的一次 embedding 调用（失败静默降级）。

### DR-04 遗忘：主动周期整理（Dream），而非永不删除 / 纯 TTL

- **候选**：(a) 只增不删（存储便宜）；(b) 纯 TTL 过期；(c) 周期性多策略整理
- **决策**：(c)
- **理由**：(a) 是慢性死亡——重复条目使检索结果同质化，密钥永久驻留是安全事故（NFR-6），prompt 注入预算被垃圾占据；(b) TTL 一刀切无法区分"过时的日志"和"三个月前但仍然正确的用户偏好"——后者靠 facts 层的 carry-forward 和条目的 `last_accessed` 续命。整理组合了四个正交策略（去重/剪枝/聚合/清秘），每个针对一种腐化模式。参考 Generative Agents 的 reflection（聚合）+ 艾宾浩斯遗忘曲线（剪枝阈值 30 天）。
- **代价**：整理有误删风险（70% 重叠阈值可能合并语义不同的条目）——用 preview/apply 两段式保留未来加人工门的能力；O(n²) 去重是规模天花板（DR-08）。

### DR-05 检索底座：内嵌 SQLite（FTS5 + sqlite-vec），而非外部检索服务

- **候选**：(a) Elasticsearch/OpenSearch；(b) 独立向量库；(c) SQLite FTS5 + sqlite-vec 扩展
- **决策**：(c)
- **理由**：NFR-3（零部署）是硬约束——本地桌面产品要求 `pip install` 即完整功能。FTS5 内建于 SQLite（BM25 免费可得）；sqlite-vec 是单文件扩展，装不上就降级（可选依赖而非硬依赖）。每 Agent 一个独立 sqlite 文件，天然隔离，删 Agent 即删索引。
- **代价**：sqlite-vec 无 ANN 索引（暴力扫描），十万级向量后变慢——百级条目下无感；FTS5 的 unicode61 分词对中文按字切分，词组精度低于专业中文分词（由向量路和 RRF 补偿）。

### DR-06 融合算法：RRF，而非加权分数融合

- **候选**：(a) 归一化分数加权（`α·BM25 + (1-α)·cosine`）；(b) Reciprocal Rank Fusion
- **决策**：(b)
- **理由**：BM25 分数与余弦相似度**量纲不可比**，归一化系数 α 需要针对语料调参——本系统每个 Agent 的记忆语料都不同，不存在全局最优 α。RRF 只用排名不用分数，免调参、对离群分数鲁棒，且是 IR 文献的成熟默认（Cormack et al. 2009，k=60）。
- **代价**：丢弃分数幅度信息——"远超第二名的第一名"和"险胜的第一名"权重相同（top-5 场景影响可忽略）。

### DR-07 偏好学习：启发式 + 置信度计数，而非 LLM 判断

- **候选**：(a) 每轮让 LLM 总结用户偏好；(b) 正则/统计启发式 + 出现 3 次才写入
- **决策**：(b)
- **理由**：偏好学习每轮对话都要跑（高频路径），LLM 方案的成本随对话线性增长且输出不稳定（同样的对话可能总结出不同偏好，写入会震荡）。启发式检测的四个维度（语言/详细度/术语密度/风格关键词）都是表层统计特征，正则足够；置信度 3 次消除单次偶然。深层偏好（"用户讨厌过度抽象"）交给编译层的 LLM 蒸馏去捕捉——**两套机制按信号深度分工**。
- **代价**：只能学到表层偏好；检测器是硬编码清单，新维度要改代码。

### DR-08 去重算法：关键词重叠 O(n²)，而非 embedding 聚类

- **候选**：(a) embedding 相似度聚类（语义准确）；(b) 关键词集合重叠（`|A∩B|/min(|A|,|B|)`）
- **决策**：(b)，代码中以 `ponytail` 注释显式标记天花板
- **理由**：Dream 在对话收尾同步跑（NFR-1 要求它绝不能失败或过慢）；embedding 方案给每次整理引入 O(n) 次网络调用和一个可失败依赖。关键词重叠零依赖、可解释（能打印出"因为共享这些词所以合并"）、在"同一任务反复出现"这一主要重复模式下召回足够。
- **代价**：改述型重复（同义不同词）漏检；O(n²) 在千级条目后需换 embedding 聚类——升级路径已在注释中写明。

### DR-09 写入门槛：had_tools，而非全量记录 / LLM 判重要性

- **候选**：(a) 每轮都记；(b) LLM 评估"这轮值得记吗"；(c) 用过工具才记
- **决策**：(c)
- **理由**："用没用工具"是**免费且客观**的重要性代理指标——用了工具说明产生了副作用或做了真实查询，纯问答闲聊则大概率无长期价值。(b) 每轮多一次 LLM 调用且判断标准漂移；(a) 让流水膨胀、编译成本上升。
- **代价**：纯对话中的重要信息（"我们下周迁移到 PG"）会漏记——由偏好学习和用户主动 `memory_ops.add` 部分补偿。

### DR-10 记忆内容取向："关于用户的事实"，而非"执行日志"

- **候选**：(a) 记录完整执行轨迹（利于回放/审计）；(b) 只蒸馏用户相关事实
- **决策**：(b)，通过蒸馏 prompt 的负面清单强制（"不要文件名、工具调用、命令输出"）
- **理由**：执行轨迹另有归宿（会话消息表、checkpoint）；记忆的唯一消费场景是**注入未来对话的 prompt**——那里需要的是"用户偏好 pytest"而不是"上周三 shell 返回了什么"。混入日志会同时毒化编译质量和检索相关性。
- **代价**：放弃了从记忆做执行审计的可能性（用会话存档补）。

### DR-11 作用域：agent/project 双域，而非单域或自由标签

- **候选**：(a) 单一作用域；(b) 自由 tag 体系；(c) 固定双域 agent/project
- **决策**：(c)
- **理由**："我个人的经验"和"这个项目的共识"消费优先级不同——project 记忆检索时排前（项目事实比个人习惯更可能是当前任务的硬约束）。自由 tag 需要治理（谁定 tag、怎么归并），双域是够用的最小分类。
- **代价**：粒度粗；project 域目前缺自动写入口（见第 12 章已知局限）。

---

## 8. 参考设计对照表

| 参考 | 借鉴了什么 | 有意不同之处 |
|---|---|---|
| **Stanford Generative Agents**（Park et al. 2023） | memory stream（流水）→ reflection（Dream 模式提取）的两级结构 | 不做 importance scoring 打分检索（LLM 打分成本高），用 RRF 混合检索替代 |
| **MemGPT / Letta**（Packer et al. 2023） | "上下文有限，记忆必须外置+分级"的核心问题定义 | 拒绝 LLM 自主分页——分层调度全部由代码确定性完成（与执行引擎"宏观确定性"哲学一致） |
| **ChatGPT Memory**（OpenAI） | "从对话自动提取耐久用户事实"（对应 facts 层） | 事实提取离线批量做（每 5 次对话），不在对话轮内实时抽取 |
| **Claude Code auto-memory** | 明文 md 文件 + 索引的透明记忆形态；"记忆是用户资产"取向 | 增加了 LLM 编译层与自动遗忘（Claude Code 靠人工维护索引） |
| **Mem0 / Zep** | add/search/update/delete 的记忆 API 形态（对应 memory_ops 工具） | 不做托管服务，全本地 |
| **Atkinson–Shiffrin 记忆模型** | 感觉登记→短时→长时的三级分层隐喻 | — |
| **艾宾浩斯遗忘曲线** | "不复习即衰减"→ 30 天未访问剪枝 | 简化为硬阈值而非连续衰减函数 |
| **Cormack et al. 2009（RRF）** | 融合算法与 k=60 默认值 | — |
| **QoderWake**（逆向调研对象） | 记忆自进化的产品定位；SQLite+sqlite-vec 本地检索栈 | 其记忆库表结构未公开，本设计为独立实现 |

---

## 9. 失效模式与降级矩阵

| 失效 | 影响 | 降级行为 |
|---|---|---|
| embedding 端点不可用 | 向量检索失效 | 静默降为纯 FTS5 |
| sqlite-vec 扩展装不上 | 同上 | `_has_vec=False`，FTS5 继续 |
| FTS5 查询语法错误（特殊字符） | 单次检索失败 | 降为关键词全文件扫描 |
| search.sqlite 损坏 | 索引不可用 | 检索走扫描；删除文件可重建索引 |
| 编译 LLM 调用失败 | 本轮不产出新摘要 | 沿用上一版编译产物（指纹未更新，下次重试） |
| Dream 中途异常 | 部分整理未完成 | 逐条 try/except，错误记入 `DreamReport.errors`，不回滚已完成动作 |
| 记忆写入失败 | 本轮对话不落忆 | `reply_stream` 外层 try/except 吞掉，对话正常返回 |
| memory 目录被用户手工删除 | 全部遗忘 | 下轮对话自动重建目录结构，从零积累 |

**总原则**：记忆系统的每一层都假设下一层可能不存在。

---

## 10. 安全与隐私设计

1. **入口检查**：`memory_ops.add` 写入前做敏感内容检查（`_check_sensitive`）
2. **驻留清除**：Dream 清秘用 8 组正则兜底捕捉已落库密钥（防其他写入路径遗漏）
3. **本地化**：全部数据在 `~/.agent-smith/` 本地目录，无云端同步
4. **可否认**：用户可直接删除任意 .md 条目文件，索引下次整理时自愈
5. **路径安全**：条目 id 为受控生成的 12 位 hex，文件名不接受外部输入拼接

---

## 11. 验收标准（供验收 Agent 逐条核实）

| ID | 标准 | 核实方式 |
|---|---|---|
| AC-1 | 流式对话（用过工具）结束后，`recent.jsonl` 新增一行、`memory/agent/` 新增条目 | 行为测试（已有：scratchpad `test_e2e_memory.py` §4） |
| AC-2 | 与用户消息相关的记忆条目出现在 system prompt 的 `## Relevant Memories` 块中 | 行为测试（同上 §3） |
| AC-3 | 会话最近 10 条消息按序进入 LLM 上下文（system 之后、当前消息之前） | 行为测试（同上 §2） |
| AC-4 | 编译具有幂等性：输入未变时重跑 `run_compilation` 不产生 LLM 调用（指纹命中） | 代码核实 `compile.py` 指纹逻辑 + 可选行为测试 |
| AC-5 | 含密钥（如 `sk-` 开头 token）的条目在 Dream `apply()` 后被删除 | 行为测试或代码核实 `dream.py` `_SECRET_PATTERNS` |
| AC-6 | 检索降级链完整：无 embed → FTS5；FTS5 异常 → 关键词扫描；全失败 → 空串，主流程不抛异常 | 代码核实 `store.search` / `search_relevant_memories` 异常路径 |
| AC-7 | 同一偏好信号第 3 次出现时写入 `context.md`，且只填 `{{to_be_learned}}` 占位符、不覆盖已有值 | 代码核实 `user_learner.py` |
| AC-8 | 被动注入 token 有界：编译层字符上限 + 检索 top-5 × 200 字符截断 | 代码核实 `compile.py` prompt 约束 + `search_relevant_memories` 截断 |
| AC-9 | 记忆链路人为致障（如删除 memory 目录权限 / 断网 embedding）时对话仍正常完成 | 代码核实全链路 try/except（NFR-1） |

**验收判定**：9 条全数核实为"符合"→ 文档转「已验收」；任一条不符 → 记录差异（文档错 → 改文档；代码错 → 开缺陷）。

---

## 12. 已知局限与演进路线

| 局限 | 影响 | 演进 |
|---|---|---|
| embedding 端点复用 LLM `base_url` | 常见端点（GLM 等）无 `/embeddings`，向量路静默降级为 FTS5 | 配置层增加独立 `embedding_base_url`（优先级最高的待办） |
| `project` 域无自动写入口 | 跨 Agent 共识层空转 | 在编译层增加"项目事实"判别，或团队会话落 project 域 |
| 非流式 `reply()` 的 `had_tools` 恒为 True | 非流式路径闲聊也落忆 | 与流式一致改为事件跟踪（非流式当前非主路径，优先级低） |
| Dream 去重 O(n²) + 关键词法 | 千级条目后变慢、改述型重复漏检 | 换 embedding 聚类（DR-08 已预留升级路径） |
| 模式提取产物信息量低（关键词罗列） | Pattern 条目对检索帮助有限 | 用 LLM 生成模式摘要替代关键词拼接 |
| 编译触发绑定对话计数（每 5 次） | 低频使用的 Agent 编译滞后 | 增加基于时间的触发（如每日首次对话强制编译） |
| ~~`memory_ops` 工具与 store 目录布局不一致~~（已修复 2026-07-05） | 工具已按 scope 写子目录、跨目录检索、补 `last_accessed`，互通性测试 5/5 通过 | 残余：工具写入不进 search.sqlite 索引——为 `memory_ops.add` 补索引写入 |
| 编译层字符限幅为提示词软约束 | LLM 超限时注入量轻微超预期 | `assemble_memory` 增加代码级截断，使 NFR-2 完全由代码保证 |
| 记忆目录仍依赖 `employees/<id>` 旧 profile path | 文档和代码心智容易回到数字员工模型 | 目标路径改为 `~/.agent-smith/agent/memory/`，代码层增加 `agent_dir` 适配并逐步迁移 |

---

## 13. 附：与执行引擎其他子系统的关系

- **Prompt 组装**：记忆段位于 12 段中的第 11 段（0-based index 10），裁剪优先级 5——预算不足时先于身份被裁（记忆是增强不是身份）
- **门禁哲学同源**：条目的 `Evidence` 字段与门禁"要证据不要口号"是同一条设计公理在两个子系统的投影
- **宏观确定性**：编译/Dream/学习的调度全部由代码触发（计数器、指纹、阈值），LLM 只负责蒸馏内容本身——与执行引擎"宏观确定性、微观自由度"的总哲学一致

---

## 14. 验收记录

| 项 | 内容 |
|---|---|
| 验收时间 | 2026-07-05 |
| 验收方 | 独立验收 Agent（对照代码逐条核实 + 运行行为测试，与文档作者非同一会话上下文） |
| 判定 | **PASS-WITH-CORRECTIONS** |
| 核实量 | AC 9 条（初验 8 符合 / AC-9 不符）；技术断言抽查 32 条（7 处不符）；行为测试 5/6 PASS（1 项为验收环境缺 fastapi，非缺陷） |
| 代码修正（3 处） | ① `reply()` 落忆+偏好学习补 try/except、`reply_stream()` 偏好学习补保护——修复 AC-9 缺口（agent_loop.py）；② 编译各层字符限幅指令统一到任务提示词，消除共享 system prompt "Max 400" 与 longterm 600 / facts 500 的冲突（compile.py）；③ Dream 去重段补 O(n²) 天花板与升级路径注释，使 DR-08 断言为真（dream.py） |
| 文档修正（8 处） | §0 状态、NFR-2 与 §4.2/DR-03（软约束如实表述）、§4.4（L2 距离）、§4.5（单一事实源改为单向可见+缺陷登记）、§4.6（36 个术语）、§6（失败语义两级化）、§12（新增 2 条局限）、§13（记忆段为第 11 段） |
| 复验 | 代码修正后 AC-9 转符合；行为测试回归通过（见验收后回归） |
| 遗留缺陷 | ~~`memory_ops` 与 store 目录布局不一致~~——验收后已修复（scope 子目录写入 + 跨目录 search/update/remove + `last_accessed` + 旧条目自动迁移），互通性测试 5/5 通过；残余小项：工具写入暂不进 FTS 索引（§12 登记） |
