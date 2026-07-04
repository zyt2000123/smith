# 07 · QoderWake 完整产品逆向

> 调研时间：2026-07-03
> 方法：网络多源调研 + 本地逆向工程（二进制分析、JS bundle 分析、SQLite schema 分析、文件结构分析、明文配置和 prompt 完整阅读）
> 目的：为 Agent-Smith 的产品设计、架构决策和 Agent 设计思路提供完整参考
> 性质：本文件是 QoderWake 逆向工程的最终汇总，整合 05（技术调研）和 06（员工文件与技能系统）的全部发现，并补充此前未单独成文的深层分析

---

## 一、产品概况

QoderWake 是阿里巴巴旗下 Qoder 团队（国内品牌：通义灵码）于 2026 年 5 月推出的 AI 数字员工平台。与传统 AI 编码助手不同，它部署的是名为 **Waker** 的持久化 AI 智能体。每个 Waker 有名字、入职日期、工作记录，能 24/7 自主运作。

| 维度 | 详情 |
|---|---|
| 官网 | qoder.com/qoderwake |
| 文档 | docs.qoder.com/qoderwake/overview |
| GitHub | github.com/QoderAI（23 个公开仓库，核心闭源） |
| 法律实体 | Bright Zenith Private Limited（新加坡） |
| 分发 | 邀请制预览，`curl \| bash` 安装 |
| 宣称数据 | 500 万+用户，ARR 超 6000 万美元 |

### Qoder 产品家族

| 产品 | 定位 | 架构 |
|---|---|---|
| Qoder IDE | AI 编码 IDE | Electron（VS Code / Code-OSS 分支） |
| QoderWork | AI 桌面助手 | 闭源，.dmg/.exe 分发 |
| QoderWake | AI 数字员工平台 | 本地 daemon + 浏览器 Web Console |
| Qoder Remote Control | 移动端伴侣 | iOS/Android，框架未确定 |

四款产品共享 Qoder 积分体系和统一订阅。QoderWake 是最新推出的产品线，定位从"编码辅助"拔高到"数字员工"。

---

## 二、系统架构

### 2.1 架构全景图

```
+-------------------------------------------------------------------+
|                    QoderWake 技术架构                                |
+-------------------------------------------------------------------+
|                                                                     |
|  [macOS 菜单栏]  Swift / AppKit (647KB)                             |
|       │  LaunchAgent / loginitem                                    |
|       v                                                             |
|  [守护进程]  定制 Bun v1.3.14 (Zig + JSC)  110MB                    |
|       │                                                             |
|       ├──> [Web Console]  React + Vite                              |
|       │    Tailwind CSS v4.1.18 + Ant Design                        |
|       │    SWR / Marked / Mermaid / D3 / Shiki / KaTeX              |
|       │                                                             |
|       ├──> [存储层]  SQLite (76表, WAL模式)                          |
|       │    sqlite-vec 向量搜索                                       |
|       │    Git 版本化 (Memory/Skills, 18个内部仓库)                   |
|       │    Markdown 身份文件 (9文件/Worker)                           |
|       │                                                             |
|       ├──> [MCP 端点]  SSE @ localhost:19820                        |
|       │    内置 MCP 工具 (qoderwake_memory 等)                       |
|       │    外部 MCP: STDIO / SSE / Streamable HTTP / SDK            |
|       │                                                             |
|       ├──> [CLI 客户端]  Bun v1.3.14  96MB                          |
|       │    ACP = JSON-RPC 2.0 over stdio (NDJSON)                   |
|       │                                                             |
|       ├──> [插件触发器]  Python 运行时                                |
|       │    DingTalk (轮询 1min) / Aone (轮询 10min) / GitHub (Webhook)|
|       │                                                             |
|       └──> [Chrome 扩展]  Manifest V3                               |
|            nativeMessaging + localhost HTTP                          |
|                                                                     |
|  [LLM 层]  Qwen3.7-Max/Plus | DeepSeek-V4-Pro/Flash |              |
|            GLM-5.2 | Kimi-K2.7-Code | MiniMax-M3                    |
|            Auto 路由模式 (仅国产大模型)                               |
|                                                                     |
+-------------------------------------------------------------------+
```

### 2.2 进程模型

- **Daemon**（守护进程）：长驻，监听 `127.0.0.1:19820`。启动时由 Swift 菜单栏壳拉起，或手动运行
- **Worker**：每个会话 spawn 独立子进程，使用 PGID 隔离。Worker 崩溃不影响 Daemon
- **插件进程**：Python 子进程，按触发器类型运行（polling / webhook）
- **CLI**：独立 Bun 二进制（96MB），通过 ACP 协议 over stdio 与 Daemon 通信

### 2.3 安装方式

```bash
curl -fsSL https://qoder-ide.oss-ap-southeast-1.aliyuncs.com/qoderwake/install.sh | bash
```

安装到 `~/.qoderwake/`，不污染系统目录。通过 `~/.qoderwake/bin/` 下的 symlink 暴露命令行入口。

---

## 三、目录结构

```
~/.qoderwake/
├── qoderwake                          # 主守护进程二进制 (110MB, 定制 Bun)
├── bin/                               # 命令行入口 symlinks
│   ├── qoderwake -> ../qoderwake
│   └── qoderwake-cli -> ../qodercli/qodercli-wake
├── qodercli/
│   └── qodercli-wake                  # CLI 客户端 (96MB, 定制 Bun)
│
├── .auth/                             # 认证信息
│   ├── tokens.json                    # OAuth/API tokens
│   ├── machine_id                     # 机器唯一标识
│   └── user                           # 当前用户信息
│
├── config/                            # 四层配置 (详见第四节)
│   ├── config.json                    # Daemon 级配置
│   ├── settings.json                  # 应用级配置
│   ├── feature-config.json            # Feature Flag
│   └── settings.sample.json           # 完整配置模板
│
├── data/
│   ├── store/
│   │   └── qoderwake.sqlite           # 核心数据库 (76表, ~3.7MB)
│   ├── workers/                       # Worker 运行时目录
│   │   └── <worker-id>/
│   │       ├── .qoder/                # 身份文件 (9个, 详见第五节)
│   │       ├── .qoder-plugin/         # 插件/技能/钩子
│   │       │   ├── plugin.json
│   │       │   ├── hooks/hooks.json
│   │       │   └── skills/*/SKILL.md
│   │       ├── indexes/
│   │       │   └── agent.sqlite       # Worker 级索引库
│   │       ├── memory/                # 记忆文件
│   │       ├── sessions/              # 会话运行时数据
│   │       └── workspace/             # 工作目录
│   ├── team-groups/                   # 多 Agent 群组数据
│   └── browser-connector/             # 浏览器连接器数据
│
├── plugins/                           # 已安装插件
│   ├── registry.json                  # 插件注册表
│   ├── aone/                          # Aone 插件 (Python)
│   ├── dingtalk/                      # 钉钉插件 (Python)
│   └── github/                        # GitHub 插件 (TypeScript)
│
├── resources/                         # 内置资源
│   ├── builtin-skills/                # 内置技能 (9个)
│   │   ├── planning/SKILL.md
│   │   ├── code-review/SKILL.md
│   │   ├── testing-strategy/SKILL.md
│   │   ├── sde-debug/SKILL.md
│   │   ├── architecture/SKILL.md
│   │   ├── system-design/SKILL.md
│   │   ├── change-validation-planner/SKILL.md
│   │   ├── git-worktree-branch/SKILL.md
│   │   └── qoderwake-assistant/SKILL.md
│   ├── security/
│   │   └── tool-guard-rules/
│   │       └── dangerous_shell_commands.json  # 24条安全规则
│   ├── triggers/                      # 触发器模板
│   ├── chrome-extension/              # Chrome 扩展包
│   ├── sqlite-vec/
│   │   └── vec0.dylib                 # 向量搜索 SQLite 扩展
│   ├── build-info/
│   │   └── bun_version                # = "1.3.14"
│   └── output-styles/
│       └── qoderwake_output_style.md  # 输出风格定义
│
├── extensions/                        # 扩展 (如 onboarding)
├── logs/                              # 日志文件
└── run/                               # 运行时状态 (PID, sockets)
```

---

## 四、配置系统

QoderWake 使用四层配置，优先级从低到高：

### 4.1 config.json — Daemon 级

控制守护进程的基础设施行为：

| 配置项 | 说明 | 示例值 |
|---|---|---|
| 更新通道 | stable / beta / nightly | `"stable"` |
| API 绑定 | 监听地址和端口 | `"127.0.0.1:19820"` |
| 日志轮转 | 日志大小上限和保留数 | `10MB / 5个` |
| 遥测 | 匿名使用数据收集开关 | `true` |
| 触发数据保留 | 触发运行数据保留天数 | `14` |

### 4.2 settings.json — 应用级

控制产品行为和功能开关：

| 配置项 | 说明 | 示例值 |
|---|---|---|
| 存储后端 | SQLite 或 PostgreSQL | `"sqlite"` |
| 语言 | 界面语言 | `"zh-CN"` |
| IM 渠道开关 | 各 IM 渠道独立开关 | `{dingtalk: true, feishu: false}` |
| 开机自启 | 是否随系统启动 | `true` |
| 触发队列并发 | 全局最大 / 每 Worker 最大 | `20 / 5` |
| 项目分析开关 | 是否自动分析项目 | `true` |

### 4.3 feature-config.json — Feature Flag

控制实验性功能的渐进式发布：

```json
{
  "team-chat": true,
  "workflow-v2": false
}
```

当前已开启：`team-chat`（多 Agent 群聊）。

### 4.4 settings.sample.json — 完整配置模板

包含所有可配置项的注释版模板，供用户参考。这是唯一包含行内注释的配置文件。

---

## 五、Worker 身份文件系统

每个 Worker 在 `.qoder/` 下有 **9 个身份文件**，构成完整的数字员工人格定义：

### 5.1 文件清单与职责

```
.qoder/
├── IDENTITY.md              # "我是谁" — 核心使命定义
├── PERSONA.md               # "我怎么工作" — 行为风格定义
├── BIBLE.md                 # "我按什么流程交付" — 完整 SOP
├── TOOLS.md                 # "我能用什么工具" — 工具配置与最佳实践
├── USER.md                  # "我的用户是谁" — 用户偏好（自动学习填充）
├── MEMORY.md                # "我记得什么" — 记忆索引
├── CORE_CAPABILITIES.md     # "我的核心能力" — JSON 数组
├── WORK_STYLES.md           # "我的工作风格" — JSON 数组
└── DELIVERY_COMMITMENTS.md  # "我的交付承诺" — JSON 数组，按任务类型定义管线
```

### 5.2 IDENTITY.md 结构

```markdown
# Core Mission
[一句话描述这个 Worker 的存在目的]

# Non-Negotiable Principles
1. Contract-first — 先确认契约再动手
2. Compatibility-first — 兼容性优先于创新
3. Minimal-diff — 最小改动原则
4. Boundary completeness — 边界条件必须覆盖
5. Evidence over intuition — 证据优于直觉

# Done Criteria
[什么情况下算"完成"]

# Anti-Goals
[明确不做什么]
```

IDENTITY 是最高优先级的身份文件，定义了 Worker 的本质使命和不可妥协的原则。

### 5.3 PERSONA.md 结构

```markdown
# Working Style
[简短描述偏好的工作方式]

# Decision Heuristics
When [情况X]: do [行动Y]
When [情况A]: do [行动B]
...

# Good Habits
- [好习惯列表]

# Anti-Patterns
- [要避免的反模式列表]
```

PERSONA 控制"怎么工作"而非"做什么"。它与 IDENTITY 的区别是：IDENTITY 定义方向，PERSONA 定义风格。

### 5.4 BIBLE.md 结构（核心，最复杂）

BIBLE 是最长的身份文件，后端 Worker 约 **600 行**，前端 Worker 约 **285 行**。包含完整的工作流 SOP：

```markdown
# Git Discovery Protocol
[如何发现和理解 git 仓库]

# Worktree Flow
[git worktree 隔离工作流]

# Task Assessment
[任务类型判断路由]

# Available Skills
| Skill | When to Use |
|---|---|
| planning | 功能开发前 |
| sde-debug | Bug 修复 |
| ... | ... |

# Mandatory Routing Contract
[强制技能链定义 — 详见第六节]

# Common Steps
1. Understand → Understanding Gate
2. Investigate → (varies)
3. Implement → Contract Alignment Gate
4. Skill Rubric Gate → (retry policy)
5. Verify → Validation Gate
6. Push & PR → PR Gate
7. Deliver → Test Delivery Gate

# Cross-Cutting Principles
[跨步骤的通用原则]
```

### 5.5 其余文件

| 文件 | 格式 | 用途 |
|---|---|---|
| TOOLS.md | Markdown | 列出可用工具及其使用最佳实践 |
| USER.md | Markdown 模板 | 用户信息占位符，通过 `memory_add` 自动填充 |
| MEMORY.md | Markdown | 记忆索引，指向 `memory/` 下的具体文件 |
| CORE_CAPABILITIES.md | JSON 数组 | `[{name, description}]` 声明核心能力 |
| WORK_STYLES.md | JSON 数组 | 工作风格标签 |
| DELIVERY_COMMITMENTS.md | JSON 数组 | 按任务类型定义工作流管线 |

### 5.6 设计洞察

**9 文件分离的核心价值**：每个文件独立可替换。要改变一个 Worker 的行为风格只需替换 PERSONA.md，要改变工作流只需替换 BIBLE.md，而 IDENTITY.md 保持不变。这使得"同一使命、不同风格"和"同一风格、不同流程"都可以通过文件组合实现。

---

## 六、Agent 执行模型（核心设计）

这是 QoderWake 最有价值的设计层。它定义了 Agent 如何接收任务、路由到正确的工作流、通过门禁验证质量、以及在失败时自动回退。

### 6.1 任务路由（Step 0 — Assess）

Worker 收到任务后首先进行类型评估：

```
收到任务
  │
  ├── 是否检测到评估器 artifact？
  │     └── 是 → Evaluation-Sensitive 模式（谨慎行为，避免作弊）
  │
  ├── 任务类型判断
  │     ├── Bug Fix → 走 Bug Fix 路由
  │     ├── Feature Dev → 走 Feature 路由
  │     └── 简单/直接任务 → Direct Dispatch（跳过技能链）
  │
  └── 判断依据
        ├── 关键词匹配（fix / bug / error / broken / feature / add / implement）
        ├── 上下文线索（stack trace / error log / 新需求描述）
        └── 用户显式指定
```

**Evaluation-Sensitive Signal**：Worker 会自动检测当前环境是否存在评估器 artifact（如自动测试框架、benchmark runner）。如果检测到，Worker 进入受限模式，避免产生可能"作弊"的行为（如直接 hardcode 测试用例的预期输出）。

### 6.2 强制技能链（Mandatory Routing Contract）

这是 BIBLE.md 中最关键的部分 -- 定义了哪些技能必须按顺序执行，不可跳过：

#### Feature 路由

```
planning → (architecture, 仅大型变更) → testing-strategy → change-validation-planner → code-review
```

#### Bug Fix 路由

```
sde-debug → planning → testing-strategy → change-validation-planner → code-review
```

**硬规则**：

- Bug Fix 路由**必须**使用 `sde-debug` 和 `testing-strategy`，不可用其他技能替代
- Feature 路由中 `architecture` 仅在变更涉及 3+ 文件或跨模块时触发
- `code-review` 始终是最后一步，且不可跳过
- 强制链中的每个技能都有独立的门禁（Gate），必须通过才能进入下一步

### 6.3 门禁系统（13+ Gates）

门禁是质量保证的核心机制。每个门禁有明确的通过条件和失败处理：

| 门禁 | 位置 | 通过条件 | 失败处理 |
|---|---|---|---|
| Understanding Gate | Understand 阶段末 | 能准确复述需求 + 识别边界条件 | 回退到重新理解 |
| Design Gate | 设计阶段末 | 方案满足需求 + 无明显遗漏 | 回退到 Understand |
| Root Cause Gate | Debug 阶段末 | 有证据支持的根因分析 | 回退到 Reproduce |
| Planning Gate | Planning 技能末 | 计划步骤完整 + 有验证点 | 重新规划 |
| Contract Alignment Gate | 实现前 | 实现方案与契约一致 | 回退到 Planning |
| Test Gate | 测试策略末 | 测试覆盖关键路径 + 边界 | 补充测试 |
| Validation Gate | 验证阶段末 | 所有测试通过 + 无回归 | 回退到 Planning |
| Review Gate | Code Review 末 | 无 P0/P1 问题 | 修复后重新 Review |
| Skill Rubric Gate | 每个技能执行后 | 技能输出满足质量标准 | 最多重试 2 次 |
| Git Worktree Gate | Git 操作前 | Worktree 正确设置 + 无冲突 | 清理重建 |
| PR Gate | PR 创建前 | Commit 信息规范 + 无禁止文件 | 修复后重试 |
| Test Delivery Gate | 交付前 | 测试实际运行 + 结果附在交付中 | 补运行测试 |
| Metadata Safety Gate | 全程 | 无敏感信息泄露 | 阻断并告警 |

#### Skill Rubric Gate 的重试策略

```
技能执行完成
  │
  ├── 检查输出质量
  │     ├── 通过 → 继续下一步
  │     └── 未通过 → 评估严重程度
  │           ├── 可修复 → 重试（最多 2 次）
  │           │     ├── 第 1 次重试：调整参数/上下文重执行
  │           │     └── 第 2 次重试：换策略执行
  │           └── 不可修复 → 标记 blocked，请求人工介入
  │
  └── 2 次重试后仍未通过 → 停止，生成失败报告
```

### 6.4 回退机制

QoderWake 定义了明确的回退路径，避免 Agent 在错误方向上越走越远：

```
回退路径定义：
  Implementation 失败 → 回退到 Planning
  Design 失败 → 回退到 Understand
  RootCause 失败 → 回退到 Reproduce
  Verify 失败 → 回退到 Planning

Failure Loop Guard (P0 优先级)：
  1. 跟踪失败签名（错误类型 + 上下文 hash）
  2. 同一失败签名出现 2 次 → 停止当前策略
  3. 尝试最多 2 种替代策略
  4. 替代策略也失败 → 声明 blocked，请求人工介入
```

**Failure Loop Guard** 是防止 Agent 死循环的关键机制。它不是简单的重试次数限制，而是基于失败签名的去重：如果同样的错误以同样的方式出现两次，说明当前策略本身有问题，需要换策略而非简单重试。

### 6.5 自主执行策略

QoderWake 的默认模式是**自主执行**（Autonomous），而非询问模式：

```markdown
# 默认行为
自主执行。仅在以下情况询问用户：
1. 契约关键阻断 — 需求有多种互斥解读，无法自行判断
2. 高风险/破坏性操作 — 删除数据库、force push、修改生产配置

# 反模式（明确禁止）
- 把常规可逆操作变成确认问题
- "我是否应该创建这个文件？" → 直接创建
- "我是否应该运行测试？" → 直接运行
- "你想让我继续吗？" → 默认继续
```

这个设计选择很关键：它表明 QoderWake 的 Agent 被设计为**执行者**而非**咨询者**。大多数 AI 助手默认"先问再做"，QoderWake 反过来"先做再说"。

---

## 七、Agent 自我进化

QoderWake 在 Agent 的自我改进方面有成熟的设计。

### 7.1 记忆系统

#### 存储架构

```
记忆数据分布：
  .qoder/MEMORY.md                  # 记忆索引（入口）
  indexes/agent.sqlite              # 结构化索引库
  memory/                           # 具体记忆文件
    ├── daily/                      # 每日记忆
    ├── topic/                      # 主题记忆
    └── long_term/                  # 长期记忆
```

#### 记忆作用域

| 作用域 | 范围 | 优先级 | 用途 |
|---|---|---|---|
| agent | 跨项目 | 低 | Worker 的通用偏好和经验 |
| project | 项目内 | 高（冲突时胜出） | 项目特定的模式和约定 |

#### 记忆操作

| 操作 | 说明 | 约束 |
|---|---|---|
| `memory_search` | 搜索已有记忆 | 支持模糊匹配 |
| `memory_add` | 添加新记忆 | **必须**提供 evidence（来源证据）和 reason（记忆理由） |
| `memory_update` | 更新已有记忆 | 需要原记忆 ID |
| `memory_remove` | 删除记忆 | 需要原记忆 ID |

#### Dream 机制（记忆整理）

```
Dream 流程：
  1. preview — 分析当前记忆库，生成整理预案
  2. apply — 执行整理（合并重复、删除过期、提炼规律）
  3. 自动触发时机：会话结束后自动执行
  4. 版本化：整理前后都有 git snapshot，可 rollback
```

#### 安全约束

- **禁止**在记忆中存储秘密（密码、API key、token）
- **禁止**存储渠道标识符（群聊 ID、用户手机号）
- 每条记忆**必须**附带 evidence 字段

### 7.2 用户偏好自动学习

USER.md 初始是一个带占位符的模板：

```markdown
# User Profile
- Name: {{to_be_learned}}
- Preferred Language: {{to_be_learned}}
- Code Style: {{to_be_learned}}
- Review Preference: {{to_be_learned}}
- Communication Style: {{to_be_learned}}
```

Worker 在交互过程中通过 `memory_add` 自动观察并填充这些字段。例如：

- 用户总是用中文 → 自动记录语言偏好
- 用户偏好函数式风格 → 自动记录代码风格
- 用户反复要求详细解释 → 记录沟通偏好

### 7.3 技能自进化

Worker 可以通过 `skill manage` 工具自主改进技能：

```
技能进化操作：
  patch  — 修补现有技能的某个步骤
  edit   — 编辑技能的完整内容
  write_file — 写入新版本技能文件
  create — 从零创建新技能

版本管理（SkillStore）：
  - 每次修改自动生成新版本
  - 保存完整 diff 历史
  - 支持 rollback 到任意历史版本
  - git 版本化存储
```

**重要限制**：

- Marketplace 下载的技能：只读，不可自进化
- 内置技能（builtin-skills/）：只读，不可自进化
- 仅 Worker 自己安装或创建的技能可以自进化

### 7.4 五维经验系统

QoderWake 的经验系统分为五个维度：

| 维度 | 机制 | 说明 |
|---|---|---|
| 定时回报 | cron 驱动的周期任务 | 定时汇报工作进展、生成日报/周报 |
| 能力自扩展 | 动态技能 install/upgrade/rollback | Worker 可以自主从 marketplace 安装技能 |
| 记忆自整理 | dream + snapshot + rollback | 会话后自动整理记忆，去重、合并、提炼 |
| 项目感知 | 多仓库 + onboarding + 项目记忆 | 自动分析项目结构并生成理解文档 |
| Waker 导出复制 | zip 导出用于团队分发 | 将成熟 Worker 的全部配置打包分享 |

---

## 八、System Prompt 组装顺序

这是 QoderWake 向 LLM 发送的系统提示词的精确组装顺序，直接决定了 Agent 的行为：

```
System Prompt 组装序列：

 1. IDENTITY.md            — 核心使命（最高优先级）
 2. PERSONA.md             — 行为风格
 3. BIBLE.md               — 工作流 SOP（最长，~600行）
 4. TOOLS.md               — 可用工具
 5. USER.md                — 用户偏好
 6. MEMORY.md              — 记忆索引
 7. CORE_CAPABILITIES.md   — 能力声明
 8. DELIVERY_COMMITMENTS.md— 交付承诺
 9. WORK_STYLES.md         — 风格标签
10. Output Styles          — qoderwake_output_style.md（输出格式）
11. Skills                 — 动态加载（via tool-namespace-registry.json）
12. Extensions             — 按需加载（如 onboarding）
13. Session Context        — 运行时上下文
      ├── wakerId          — 当前 Worker ID
      ├── projectId        — 当前项目 ID
      ├── project memory   — 项目级记忆
      ├── agent memory     — Worker 级记忆
      └── env vars         — 环境变量
```

**设计洞察**：

1. IDENTITY 在最前面，确保使命定义在所有后续内容之上
2. BIBLE 紧跟在 PERSONA 之后，因为它是最复杂也最重要的执行指令
3. 记忆和能力声明在中间，因为它们是上下文信息而非核心指令
4. Skills 和 Extensions 在后面动态加载，避免不必要的 token 消耗
5. Session Context 在最后，提供运行时上下文

---

## 九、技能系统

### 9.1 SKILL.md 格式

```yaml
---
name: my-skill-name
description: "技能描述，出现在技能列表和搜索结果中"
argument-hint: "可选，参数提示文本"
version: "1.0.0"
---
# Skill 正文

## 目标
[这个技能要达成什么]

## 步骤
1. [步骤 1] → 验证: [检查点]
2. [步骤 2] → 验证: [检查点]
...

## 输出格式
[期望的输出结构]

## 参数
@$1 — 第一个参数占位符
@$2 — 第二个参数占位符
```

Markdown 正文就是给 AI 的执行指令。`@$1` 语法用于参数占位。

### 9.2 内置技能清单（9 个）

| 技能 | 用途 | 触发场景 |
|---|---|---|
| `planning` | 制定实现计划 | Feature 路由的第一步 |
| `code-review` | 代码审查 | 所有路由的最后一步 |
| `testing-strategy` | 测试策略制定 | Feature/Bug 路由中段 |
| `sde-debug` | 结构化调试 | Bug Fix 路由的第一步 |
| `architecture` | 架构设计 | 大型 Feature 变更 |
| `system-design` | 系统设计 | 新系统/模块设计 |
| `change-validation-planner` | 变更验证计划 | 实现后、Review 前 |
| `git-worktree-branch` | Git Worktree 管理 | 需要分支隔离时 |
| `qoderwake-assistant` | QoderWake 元管理 | 管理 Worker 自身 |

### 9.3 QoderWake Assistant（元技能）

`qoderwake-assistant` 是一个特殊的"元技能"，用于管理 Worker 自身。它包含 **11 个管理域**：

| 管理域 | 功能 |
|---|---|
| `automation` | 管理自动任务和触发器 |
| `plugin` | 安装/卸载/更新插件 |
| `skill` | 技能 CRUD 和自进化 |
| `mcp` | MCP 服务器配置管理 |
| `project` | 项目绑定和分析 |
| `session` | 会话管理 |
| `memory` | 记忆操作（search/add/update/remove/dream） |
| `waker` | Worker 自身管理（导出/克隆等） |
| `permission` | 权限配置 |
| `im-channel` | IM 渠道管理 |
| `extension` | 扩展加载管理 |

### 9.4 Onboarding Extension（4 个技能）

这是通过 Extension 机制加载的项目入职扩展：

| 技能 | 功能 |
|---|---|
| `project-analysis` | 9 步深度仓库分析，生成 8 个理解文档 |
| `project-assistant` | 多项目发现 + 文档维护 |
| `communication-aone` | Aone 工单自动化 |
| `communication-github` | GitHub Issue 自动化 |

#### project-analysis 的 9 步流程

1. 扫描目录结构
2. 识别技术栈和框架
3. 分析 package.json / requirements.txt 等依赖
4. 解析构建配置
5. 扫描 API 端点和路由
6. 分析数据模型和 schema
7. 识别测试框架和覆盖率
8. 分析 CI/CD 配置
9. 生成 8 个标准化文档

输出的 8 个文档：项目概览、技术栈、架构图、API 文档、数据模型、测试策略、构建部署、开发指南。

---

## 十、插件系统

### 10.1 插件框架

```json
// plugin.json schema: qoderwake.plugin.v1
{
  "schema": "qoderwake.plugin.v1",
  "name": "plugin-name",
  "version": "1.0.0",
  "description": "插件描述",
  "skills": [
    { "path": "skills/my-skill/SKILL.md" }
  ],
  "mcpServers": {
    "server-name": {
      "command": "node",
      "args": ["server.js"],
      "transport": "stdio"
    }
  }
}
```

### 10.2 Aone 插件 (v1.0.3)

| 维度 | 详情 |
|---|---|
| 触发方式 | Polling（轮询） |
| 轮询间隔 | 10 分钟 |
| 退避策略 | 指数退避（失败后加倍间隔） |
| 实现语言 | Python |
| 代码规模 | 1025 行 |
| 缓存 TTL | 24 小时 |
| 功能 | 自动拉取 Aone 工单，转换为 Worker 任务 |

### 10.3 钉钉插件 (v1.0.12)

| 维度 | 详情 |
|---|---|
| 触发方式 | Polling（轮询） |
| 轮询间隔 | 1 分钟 |
| 实现语言 | Python |
| 代码规模 | 1224 行 |
| 群聊行为 | 仅响应 @mention |
| 防环措施 | 精细的自消息过滤 |
| 附件处理 | 支持图片和文件的接收与处理 |

**钉钉插件的防环设计**值得注意：Worker 在群聊中发送消息后，这条消息会被轮询器再次拉取。插件必须识别并过滤自己发出的消息，否则会形成无限循环。v1.0.12 的成熟度（12 个版本迭代）说明这个问题的复杂性。

### 10.4 GitHub Hook (v1.0.0)

| 维度 | 详情 |
|---|---|
| 触发方式 | Webhook |
| 实现语言 | TypeScript |
| 事件类型 | `issues.opened` / `issues.edited` / `pull_request.opened` / `pull_request.edited` |
| 版本 | v1.0.0（初始版本） |

---

## 十一、安全体系

### 11.1 Tool Guard（24 规则，7 类别）

`dangerous_shell_commands.json` 定义了 24 条规则，分 7 个类别：

| 类别 | 规则数 | 说明 | 示例 |
|---|---|---|---|
| `command_injection` | 4 | 防注入攻击 | 管道拼接、反引号执行 |
| `resource_abuse` | 3 | 防资源滥用 | fork 炸弹、无限循环、大文件创建 |
| `code_execution` | 4 | 防任意代码执行 | eval、exec、动态 import |
| `network_abuse` | 3 | 防网络滥用 | 数据外传、反向 shell、端口扫描 |
| `sensitive_file_access` | 4 | 防敏感文件访问 | /etc/passwd、~/.ssh/、.env |
| `privilege_escalation` | 3 | 防权限提升 | sudo、chmod 777、setuid |
| `shell_evasion` | 3 | 防 shell 规避 | 编码绕过、history 篡改、别名覆盖 |

每条规则的结构：

```json
{
  "id": "rule-001",
  "tools": ["shell", "bash"],
  "params": ["command"],
  "category": "command_injection",
  "severity": "critical",
  "patterns": ["正则表达式数组"],
  "excludePatterns": ["排除模式数组"],
  "description": "规则描述",
  "remediation": "如何修复"
}
```

### 11.2 权限分层

| 层级 | 范围 | 机制 |
|---|---|---|
| tool-guard | 工具调用层 | 24 规则正则匹配，拦截危险命令 |
| file-guard | 文件访问层 | 工作目录白名单，禁止访问目录外文件 |
| builtin-tools | 内置工具层 | 工具级权限声明（read-only / write / execute） |
| model-security | 模型交互层 | Prompt 注入防护，输出安全过滤 |

### 11.3 会话作用域安全

```
默认规则：
  - 每个 Worker 只能修改自己的文件和配置
  - 跨 Worker 操作需要用户确认
  - 破坏性操作必须先回显命令内容，再等待确认

IM 控制模式（最严格）：
  - 通过 IM（钉钉/飞书等）触发的任务使用受限权限
  - 不允许执行破坏性命令
  - 文件操作限制在项目目录内
  - 网络访问受限
```

### 11.4 Git 安全

```
Git 安全策略：
  1. 强制 Worktree 隔离 — 所有代码修改必须在 worktree 中进行
  2. 禁止直接编辑主干 — trunk (main/master) 不可直接修改
  3. PR 后自动清理 — Worktree 在 PR 合并后自动删除
  4. 提交前检查 — 禁止提交 .env、密钥文件等敏感内容
```

---

## 十二、通信协议

### 12.1 协议全景

| 通信路径 | 协议 | 传输 | 用途 |
|---|---|---|---|
| Web Console <-> Daemon | HTTP + SSE | TCP @ localhost:19820 | 前端交互 |
| CLI <-> Daemon | ACP (JSON-RPC 2.0) | stdio (NDJSON) | 命令行操作 |
| Chrome 扩展 <-> Daemon | nativeMessaging + HTTP | Chrome API + TCP | 浏览器集成 |
| 内置 MCP | SSE | HTTP @ /api/internal/builtin-mcp/ | Agent 内部工具 |
| Cloud Agents | HTTP/REST + SSE | HTTPS + Bearer Token | 云端 Agent API |
| 插件 <-> Daemon | HTTP | localhost | 触发器回调 |

### 12.2 ACP 协议细节

ACP (Agent Communication Protocol) 是 QoderWake 自定义的 CLI 通信协议：

- 基于 **JSON-RPC 2.0** 规范
- 传输层使用 **stdio**（标准输入/输出）
- 消息格式：**NDJSON**（每行一个 JSON 对象）
- 支持双向通信（CLI 发请求，Daemon 推事件）
- 官方演示仓库：`github.com/QoderAI/qoder-acp-demos`

---

## 十三、API 端点（200+）

守护进程在 `localhost:19820` 暴露超过 200 个 REST API 端点。按域分组：

### 13.1 Agent 管理

```
/api/agents/           GET    — 列出所有 Agent
/api/agents/:id        GET    — 获取 Agent 详情
/api/agents/           POST   — 创建 Agent
/api/agents/:id        PUT    — 更新 Agent
/api/agents/:id        DELETE — 删除 Agent
/api/agents/import     POST   — 导入 Agent（zip）
```

### 13.2 会话管理

```
/api/sessions/              GET    — 列出会话
/api/sessions/:id           GET    — 获取会话详情
/api/sessions/              POST   — 创建会话
/api/sessions/:id/messages  POST   — 发送消息
/api/sessions/:id/events    GET    — SSE 事件流
```

### 13.3 项目管理

```
/api/projects/              GET    — 列出项目
/api/projects/:id           GET    — 获取项目详情
/api/projects/              POST   — 绑定项目
/api/projects/:id/analyze   POST   — 触发项目分析
```

### 13.4 IM 渠道

```
/api/channels/                   GET    — 列出渠道
/api/channels/dingtalk/qr        GET    — 钉钉 QR 码
/api/channels/feishu/qr          GET    — 飞书 QR 码
/api/channels/weixin/qr          GET    — 微信 QR 码
/api/channels/wecom-bot/qr       GET    — 企微机器人 QR 码
/api/channels/:id/pair           POST   — 配对
/api/channels/:id/approve        POST   — 审批配对
/api/channels/:id/ignore         POST   — 忽略配对
```

### 13.5 插件与技能

```
/api/plugins/              GET    — 列出插件
/api/plugins/:id           POST   — 安装插件
/api/plugins/:id           DELETE — 卸载插件
/api/triggers/             GET    — 列出触发器
/api/triggers/             POST   — 创建触发器
/api/triggers/:id/runs     GET    — 触发运行历史
/api/v1/skills/            GET    — 列出技能
/api/v1/skills/            POST   — 创建技能
/api/v1/skills/:id         PUT    — 更新技能
/api/v1/skills/:id         DELETE — 删除技能
/api/skill-market/         GET    — 技能市场列表
/api/skill-market/:id      POST   — 从市场安装
```

### 13.6 认证

```
/api/auth/github/callback   GET    — GitHub OAuth 回调
/api/auth/frontend          POST   — 前端认证
/api/auth/relogin           POST   — 重新登录
```

### 13.7 知识系统（QMind）

```
/api/qmind/notebooks/         GET/POST — 笔记本 CRUD
/api/qmind/proposals/          GET/POST — 知识提案
/api/qmind/bindings/           GET/POST — 知识绑定
/api/qmind/featured/           GET      — 推荐知识
```

### 13.8 工作流

```
/api/workflows/                GET/POST — 工作流定义
/api/workflow-runs/            GET/POST — 工作流运行
/api/workflow-runs/:id/events  GET      — 运行事件流
```

### 13.9 人工介入

```
/api/human-actions/            GET/POST — 人工操作
/api/user-confirmations/       GET/POST — 用户确认
```

### 13.10 看板

```
/api/board/tasks/              GET      — 任务列表
/api/board/filters/            GET/POST — 过滤器
/api/board/summaries/          GET      — 任务摘要
```

### 13.11 远程员工

```
/api/remote-employees/         GET/POST — 远程 Worker 管理
```

### 13.12 系统管理

```
/api/v1/system/health          GET  — 健康检查
/api/v1/system/restart         POST — 重启守护进程
/api/v1/system/shutdown        POST — 关闭守护进程
/api/v1/system/update          POST — 触发更新
```

### 13.13 内部接口

```
/api/internal/builtin-mcp/     — MCP 适配器（SSE 端点）
/api/internal/permissions/     — 权限管理
/api/internal/memory-hooks/    — 记忆钩子
/api/internal/file-changes/    — 文件变更追踪
/api/v2/service/embedding      POST — 代码嵌入
/api/v2/service/sse            GET  — 通用 SSE 流
```

---

## 十四、前端技术栈

### 14.1 技术选型

| 层 | 技术 | 版本 | 逆向证据 |
|---|---|---|---|
| UI 框架 | React | 19.x | `<div id="root">`；JS bundle 中 8225 处 `jsx`、905 处 `useState`、460 处 `useEffect` |
| 构建工具 | Vite | 6.x | JS bundle 以 `const __vite__mapDeps=...` 开头；`<script type="module">` |
| CSS 框架 | Tailwind CSS | v4.1.18 | CSS 文件头注释 `/*! tailwindcss v4.1.18 */` |
| 组件库 | Ant Design (antd) | 5.x | CSS 中 1078 个 `.ant-` 前缀选择器 |
| 数据获取 | SWR | - | bundle 中存在 `swr` 标识 |
| Markdown | Marked | - | 24 处出现 |
| 图表 | Mermaid + D3 | - | 独立 chunk `mermaid-59c9be08-BY4qcIhF.js` |
| 语法高亮 | Shiki | - | 包含数十种语言语法 chunk |
| 数学公式 | KaTeX | - | 独立 chunk `katex-uyQzrBQ9.js` |

### 14.2 Bundle 分析

- 主 bundle 约 **3.8MB**（未压缩）
- Vite 代码分割（Code Splitting）：Mermaid、KaTeX、Shiki 语法包独立 chunk
- 资源由 Daemon 在 localhost:19820 提供 static serving

---

## 十五、LLM 模型支持

### 15.1 内置模型层级

通过 Qoder 积分系统使用：

| 层级 | 模型 | 定位 |
|---|---|---|
| Ultimate | Qwen3.7-Max | 最强性能，积分消耗最高 |
| Performance | Qwen3.7-Plus, DeepSeek-V4-Pro | 性能与成本平衡 |
| Efficient | DeepSeek-V4-Flash, GLM-5.2, Kimi-K2.7-Code | 快速廉价 |
| Lite | MiniMax-M3 | 最轻量 |
| Auto | 智能路由自动选择 | 根据任务复杂度自动分配 |

### 15.2 Auto 路由模式

Auto 模式会根据任务复杂度自动选择模型层级：
- 简单问答 → Lite/Efficient
- 代码生成 → Performance
- 复杂推理/架构设计 → Ultimate

### 15.3 BYOK 支持

仅在 Qoder IDE/CLI 个人版中可用，QoderWake 暂不支持：

| 提供商 | 说明 |
|---|---|
| 阿里云百炼 | Qwen 系列 |
| DeepSeek | DeepSeek-V4 系列 |
| Z.ai | 智谱 GLM 系列 |
| Kimi | Moonshot/Kimi 系列 |
| MiniMax | MiniMax 系列 |
| 小米 MIMO | 小米自研模型 |

### 15.4 不支持的提供商

**明确不支持**：OpenAI (GPT)、Anthropic (Claude)、Google (Gemini)。这是产品策略选择而非技术限制。forum.qoder.com 上有活跃的功能请求。

---

## 十六、IM 渠道集成

### 16.1 支持的渠道

| 渠道 | 状态 | 轮询间隔 |
|---|---|---|
| 钉钉 (DingTalk) | v1.0.12 | 1 分钟 |
| 飞书 (Feishu/Lark) | 支持 | - |
| 微信 | 支持 | - |
| 企业微信 (WeCom) | 支持 | - |
| QQ | 支持 | - |

### 16.2 配对流程

```
用户操作流程：
  1. 在 Web Console 打开 IM 渠道设置
  2. 选择渠道类型（钉钉/飞书/微信/企微/QQ）
  3. 扫描生成的 QR 码完成授权
  4. 系统生成配对码
  5. 在 IM 中 @Worker 发送配对码
  6. Worker 确认配对 → 配对成功
  7. 用户可选：approve（批准）/ ignore（忽略）
```

### 16.3 渠道隔离

每个渠道独立开关，通过 `settings.json` 控制。渠道间互不影响 -- 关闭钉钉不影响飞书。

---

## 十七、知识系统（QMind）

QMind 是 QoderWake 的知识管理子系统：

| 概念 | 说明 |
|---|---|
| Notebooks | 知识笔记本，类似文件夹 |
| Knowledge Action Proposals | 知识操作提案，Worker 建议添加的知识 |
| Bindings | Agent-知识绑定，哪个 Worker 可以访问哪些知识 |
| Featured Notebooks | 推荐笔记本 |

底层存储：
- 结构化元数据在 SQLite（`qmind_knowledge_bindings`, `qmind_knowledge_mutations`）
- 向量搜索通过 `sqlite-vec` 扩展（`vec0.dylib`）
- 支持语义检索，不仅是关键词匹配

---

## 十八、工作流引擎

### 18.1 基础工作流

```
工作流系统：
  workflow_definitions  — 工作流定义（版本化）
  workflow_runs        — 工作流运行实例
  workflow_events      — 运行事件流（事件溯源）
```

### 18.2 WakerFlow 多 Agent 编排

WakerFlow 是 QoderWake 的多 Agent 协作引擎：

```
WakerFlow 架构：
  Leader Waker
    │ 接收复杂任务
    │ 分解为多个 Phase
    │
    ├── Phase 1 → 分配给 Waker A
    ├── Phase 2 → 分配给 Waker B (依赖 Phase 1)
    ├── Phase 3 → 分配给 Waker C (并行)
    └── Phase 4 → Leader 汇总
```

Leader Waker 负责：
- 任务分解和分配
- 依赖管理（哪些 Phase 可以并行，哪些必须串行）
- 结果汇总和质量检查
- 失败处理和重分配

---

## 十九、定价

QoderWake 捆绑在 Qoder 统一订阅中，一个订阅覆盖所有产品线：

| 方案 | 月费 | 月度积分 | 说明 |
|---|---|---|---|
| Community | $0 | 2 周 Pro 试用 + BYOK | 免费入门 |
| Pro | $20 | 2,000 | 个人开发者 |
| Pro+ | $60 | 6,000 | 进阶用户 |
| Ultra | $200 | 20,000 | 重度用户 |

额外积分：$0.02/积分。非高峰时段积分消耗打折（Qwen3.7-Max 省 80%，Plus 省 60%）。

---

## 二十、两种 Worker 类型的差异

QoderWake 预设了不同角色的 Worker 模板，其中最核心的两种：

### 20.1 Software Developer（后端）

- BIBLE 长度：~600 行
- 核心导向：**正确性优先（Correctness-first）**
- 强制原则：Contract-first, Compatibility-first, Minimal-diff
- 完整门禁链：Understanding → Design → RootCause → Planning → Contract Alignment → Test → Validation → Review → Skill Rubric → Git Worktree → PR → Test Delivery → Metadata Safety
- 回退策略：多层嵌套回退 + Failure Loop Guard

### 20.2 Frontend Developer（前端）

- BIBLE 长度：~285 行（约为后端的一半）
- 核心导向：**视觉质量 + 正确性**
- 新增门禁：**Design Direction Gate** — 在实现前检查设计方向是否正确
- 美学护栏：
  - 字体限制（仅允许特定字体族）
  - 颜色限制（必须使用设计 token，禁止 hardcode 颜色值）
  - 间距规范（使用预定义的 spacing scale）
- 5 维前端验证：
  1. 视觉一致性（与设计稿对比）
  2. 响应式（多断点验证）
  3. 可访问性（a11y 基础检查）
  4. 性能（bundle 影响评估）
  5. 交互（状态管理正确性）

### 20.3 差异对比

| 维度 | Software Developer | Frontend Developer |
|---|---|---|
| BIBLE 行数 | ~600 | ~285 |
| 核心导向 | 正确性 | 视觉 + 正确性 |
| 专属门禁 | Root Cause Gate | Design Direction Gate |
| 美学约束 | 无 | 字体/颜色/间距限制 |
| 验证维度 | 功能 + 测试 | 功能 + 视觉 + 响应式 + a11y + 性能 |
| 设计权衡 | 兼容性 > 优雅 | 设计一致性 > 便利 |

---

## 二十一、对 Agent-Smith 的完整启示

### 21.1 直接采纳（P0）

| QoderWake 设计 | Agent-Smith 采纳建议 | 理由 |
|---|---|---|
| 9 文件身份系统 | 采用相同分离：identity.md / persona.md / bible.md / tools.md / user.md / memory.md + 能力/风格/承诺声明 | 文件分离使角色可组合、可替换 |
| SKILL.md 格式 | 直接使用 YAML frontmatter + Markdown 正文 | 简洁、人类可读、AI 可执行 |
| 安全护栏文件 | 维护 dangerous_commands.json，7 类别规则 | 低成本高收益的安全兜底 |
| 门禁系统 | 核心门禁：Understanding / Planning / Validation / Review | 防止 Agent 在错误方向越走越远 |
| 强制技能链 | Feature: planning → testing → validation → review | 确保关键步骤不被跳过 |
| 自主执行默认 | 默认做，不默认问 | 数字员工应该像真人一样执行 |
| Failure Loop Guard | 跟踪失败签名，2 次相同失败换策略 | 防止死循环的关键机制 |

### 21.2 选择性采纳（P1）

| QoderWake 设计 | Agent-Smith 采纳建议 | 取舍考量 |
|---|---|---|
| plugin.json | 可简化采用，v0 不需要完整插件系统 | 先支持 Skills，后支持 Plugins |
| hooks.json | v0 先实现 SessionStart 和 PreToolUse | 不需要 5 个钩子全上 |
| Dream 记忆整理 | v1 实现，v0 只做 memory_add/search | Dream 机制需要稳定的记忆基础 |
| Git 版本化 Memory/Skills | v1 实现，v0 用文件系统 | Git 版本化是好方案但 v0 不急需 |
| 用户偏好自动学习 | v1 实现，v0 用手动配置 | 自动学习需要足够的交互数据 |
| Worktree 隔离 | v1 实现，v0 用分支策略 | Worktree 增加复杂度 |
| 4 层配置系统 | v0 用 2 层（系统 + 用户），v1 加 Feature Flag | 避免过早复杂化 |

### 21.3 不采纳 / 差异化

| QoderWake 设计 | Agent-Smith 决策 | 理由 |
|---|---|---|
| Bun/TypeScript 运行时 | 保持 Python + AgentScope | 团队技术栈、AgentScope 成熟度 |
| Ant Design 组件库 | 使用 shadcn/Base UI | 与 LLM-Wiki-Knowledge-Hub 保持一致 |
| Swift 原生菜单栏壳 | Electron 或 daemon + 浏览器（待 spike） | Swift 开发成本高，受限 macOS |
| 仅国产模型 | 支持 OpenAI + Anthropic + 国产 | Agent-Smith 面向更广泛用户 |
| QR 码 IM 配对 | v0 不做 IM 集成 | IM 集成是 v1+ 特性 |
| 76 表 SQLite | v0 从简单 schema 开始 | 按需增长，不预设 76 表 |
| WakerFlow 多 Agent | v0 先做单员工，v1+ 再做多员工 | 先打通单员工闭环 |
| 积分/订阅制 | 不做计费，用户自备 API Key | Agent-Smith 是工具不是平台 |

---

## 二十二、核心设计哲学总结

从 QoderWake 的逆向工程中，可以提炼出 7 条核心设计哲学：

### 1. 契约驱动（Contract-Driven）

不是"先写代码后补文档"，而是"先定义契约（接口、行为、边界），再按契约实现"。IDENTITY.md 是最高契约，BIBLE.md 是执行契约，门禁是契约检查点。

### 2. 门禁密集（Gate-Intensive）

13+ 个门禁不是为了制造摩擦，而是为了**尽早发现偏离**。每个门禁都有明确的通过条件和失败处理。这比"让 Agent 自由发挥后再检查结果"高效得多。

### 3. 技能编排（Skill Orchestration）

Agent 不是一个巨大的 prompt，而是由多个原子化技能组合编排而成。强制技能链确保关键技能不被跳过，技能之间通过门禁传递质量信号。

### 4. 证据导向（Evidence-Oriented）

记忆必须附带 evidence，调试必须有 root cause 证据，PR 必须附带测试结果。整个系统的设计消除了"我觉得没问题"这种无根据的判断。

### 5. 最小信任（Minimal Trust）

Agent 对自己的信任是有限的：
- 双层验证（自检 + 独立验证器）
- Failure Loop Guard（检测重复失败）
- Skill Rubric Gate（技能输出质量检查）
- 破坏性操作强制确认

### 6. 自进化（Self-Evolution）

Agent 不是静态配置，而是持续进化的：
- 记忆系统（学习用户偏好和项目模式）
- 技能自进化（使用中改进技能定义）
- Dream 机制（自动整理和提炼经验）
- 用户偏好自动学习

### 7. 安全优先（Security-First）

安全不是事后补丁，而是架构层面的设计：
- Tool Guard 24 规则
- 4 层权限分层
- 会话作用域隔离
- Git Worktree 强制隔离
- 敏感文件访问拦截
- IM 控制模式权限收紧

---

## 附录 A：逆向工程方法

| 方法 | 工具 | 发现内容 |
|---|---|---|
| 二进制分析 | `file`, `strings`, `otool -L` | 确认 Bun/Zig/JSC 技术栈，排除 Electron |
| JS Bundle 分析 | 文本搜索 + 正则统计 | 确认 React/Vite/Tailwind/antd 前端栈 |
| SQLite Schema | `sqlite3 .schema` | 76 表结构、迁移历史、关系图 |
| 文件系统遍历 | `find`, `tree`, `ls -la` | 完整目录结构、文件用途 |
| 明文配置阅读 | 直接读取 JSON/YAML/Markdown | 4 层配置、9 个身份文件、24 条安全规则 |
| Prompt 分析 | 阅读 IDENTITY/PERSONA/BIBLE/SKILL.md | Agent 执行模型、门禁系统、强制链 |
| Git 仓库检查 | `git log`, `git show` | 记忆/技能版本化机制、提交消息格式 |
| npm 分析 | npm registry 查询 | CLI 版本历史、包大小、依赖 |
| 网络调研 | 官网、文档、GitHub、论坛 | 产品概况、定价、社区反馈 |

## 附录 B：开源组件清单

| 仓库 | 语言 | 说明 |
|---|---|---|
| `QoderAI/qoder-action` | JS / Shell | GitHub Action，OIDC 认证 |
| `QoderAI/qoder-acp-demos` | TypeScript | ACP 协议演示，确认 JSON-RPC 2.0 |
| `QoderAI/qoder-community` | Astro / TypeScript | 社区技能平台，Cloudflare Pages |
| `QoderAI/cloud-agents-sdk-go` | Go | Cloud Agents Go SDK（空仓库） |
| `QoderAI/homebrew-qoder` | Ruby | Homebrew 安装配方 |
| (第三方) `numtide/llm-agents.nix` | Nix | Nix 包定义，揭示 Bun 运行时 |
| (第三方) 泄露的 system prompts | - | 完整系统提示词 |
| (npm) `@qoder-ai/qodercli` | TypeScript | 160 版本，70.5MB |

## 附录 C：未确定项

| 维度 | 状态 | 下一步 |
|---|---|---|
| 移动端框架 | 未知 | 需下载 APK 拆包分析 |
| PostgreSQL 模式详情 | 仅知可选 | 需进一步配置分析 |
| Auto 路由算法 | 黑盒 | 需更多使用数据 |
| WakerFlow 内部协议 | 部分可见 | 需多 Agent 场景实测 |
