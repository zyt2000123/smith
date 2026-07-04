# 后端 API 参考

## 服务概览

| 项目 | 说明 |
|------|------|
| 框架 | FastAPI |
| 服务名 | Agent-Smith Server |
| 版本 | `0.2.0` |
| 运行时 | Python >= 3.11 |
| 默认端口 | `8140` |
| 数据库 | SQLite（WAL 模式，`~/.agent-smith/sqlite/agent-smith.sqlite`） |
| CORS | 全开放（`allow_origins=["*"]`，所有方法、所有请求头） |

启动命令：

```bash
cd server && uv run uvicorn app.main:app --port 8140 --reload
```

带 LLM 配置启动：

```bash
AGENTSMITH_LLM_API_KEY="sk-xxx" \
AGENTSMITH_LLM_BASE_URL="https://..." \
AGENTSMITH_LLM_MODEL="glm-4.7" \
uv run uvicorn app.main:app --port 8140
```

启动生命周期：初始化 SQLite 数据库 -> 启动后台调度器（每 60 秒 tick） -> 启动 PluginService。关闭时反向清理。

---

## 端点总览

共 11 个路由模块，23+ 个 API 端点。

| 模块 | 前缀 | 端点数 |
|------|------|--------|
| 健康检查 | `/api` | 1 |
| 认证 | `/api/auth` | 2 |
| 员工管理 | `/api/employees` | 5 |
| 会话 | `/api/employees/{employee_id}/sessions` | 5 |
| 任务 | `/api/employees/{employee_id}/tasks` | 2 |
| 自动任务 | `/api/employees/{employee_id}/auto-tasks` | 6 |
| 模板 | `/api/templates` | 1 |
| 文件 | `/api/employees/{employee_id}/files` | 3 |
| 配置 | `/api/config` | 2 |
| 统计 | `/api/employees/{employee_id}/stats` | 1 |
| 插件 | `/api/plugins` | 4 |
| 团队 | `/api/teams` | 7 |

---

## 健康检查

### GET /api/health

服务存活探针。

**响应 200：**

```json
{
  "status": "ok",
  "version": "0.2.0"
}
```

---

## 认证 `/api/auth`

> 当前为 stub 实现，未接入真实数据库校验。

### POST /api/auth/login

用户登录。

**请求体** `LoginRequest`：

| 字段 | 类型 | 必填 | 约束 |
|------|------|------|------|
| `email` | `EmailStr` | 是 | 合法邮箱格式 |
| `password` | `str` | 是 | 8-128 字符，必须同时包含字母和数字 |

**响应 200** `LoginResponse`：

```json
{
  "success": true,
  "message": "登录成功",
  "user_data": { ... }
}
```

**错误场景：**

- `422` — 密码不满足 min_length=8 / max_length=128 或缺少字母+数字

---

### GET /api/auth/health

认证服务健康检查。

**响应 200：**

```json
{
  "status": "ok",
  "service": "auth"
}
```

---

## 员工管理 `/api/employees`

### GET /api/employees

列出所有员工。

**响应 200** `list[EmployeeOut]`：

```json
[
  {
    "id": "a1b2c3d4",
    "name": "小智",
    "role": "developer",
    "device": "MacBook-Pro.local",
    "online": false,
    "description": "全栈开发助手",
    "knowledge": ["python", "fastapi"],
    "environment": "本地",
    "accent": "",
    "created_at": "2025-01-01T00:00:00"
  }
]
```

---

### POST /api/employees

创建新员工。

**流程：**
1. 生成 ID：`uuid4().hex[:8]`
2. 在数据库中创建员工记录（`device` 默认为当前主机名）
3. 从 `TEMPLATES_DIR/<role>/` 复制模板文件到 `~/.agent-smith/employees/<id>/`

**请求体** `EmployeeCreate`：

| 字段 | 类型 | 必填 | 默认值 |
|------|------|------|--------|
| `name` | `str` | 是 | — |
| `role` | `str` | 是 | — |
| `description` | `str` | 否 | `""` |
| `device` | `str` | 否 | `""` |
| `knowledge` | `list[str]` | 否 | `[]` |
| `environment` | `str` | 否 | `"本地"` |
| `accent` | `str` | 否 | `""` |

**响应 201** `EmployeeOut`

---

### GET /api/employees/{employee_id}

获取单个员工详情。

**路径参数：**
- `employee_id` — 员工 ID（8 位 hex）

**响应 200** `EmployeeOut`

**错误：**
- `404` — 员工不存在

---

### PUT /api/employees/{employee_id}

更新员工信息。仅更新请求体中提供的字段，未提供的字段保持不变。

**请求体** `EmployeeUpdate`（全部可选）：

| 字段 | 类型 |
|------|------|
| `name` | `str \| None` |
| `role` | `str \| None` |
| `description` | `str \| None` |
| `device` | `str \| None` |
| `knowledge` | `list[str] \| None` |
| `online` | `bool \| None` |
| `accent` | `str \| None` |

**响应 200** `EmployeeOut`

---

### DELETE /api/employees/{employee_id}

删除员工。同时删除数据库记录和 `~/.agent-smith/employees/<id>/` 目录下的所有文件。

**响应 204** 无内容

---

## 会话 `/api/employees/{employee_id}/sessions`

### GET .../sessions

列出指定员工的所有会话。

**响应 200** `list[SessionOut]`：

```json
[
  {
    "id": "a1b2c3d4e5f6",
    "employee_id": "a1b2c3d4",
    "title": "新对话",
    "created_at": "2025-01-01T00:00:00",
    "last_message_preview": "你好，有什么可以帮助...",
    "last_message_at": "2025-01-01T00:01:00",
    "message_count": 5
  }
]
```

> `last_message_preview`、`last_message_at`、`message_count` 通过子查询在数据库层计算。

---

### POST .../sessions

创建新会话。

**请求体** `SessionCreate`：

| 字段 | 类型 | 必填 | 默认值 |
|------|------|------|--------|
| `title` | `str` | 否 | `""`（服务层默认设为 `"新对话"`） |

**响应 201** `SessionOut`

> 会话 ID 为 `uuid4().hex[:12]`。

---

### GET .../sessions/{session_id}/messages

获取会话消息列表。按 `created_at` 升序排列。

**查询参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | `int` | `0` | 返回条数，0 表示不限制 |
| `offset` | `int` | `0` | 偏移量 |

**响应 200** `list[MessageOut]`：

```json
[
  {
    "id": "msg_a1b2c3d4e5f6",
    "session_id": "a1b2c3d4e5f6",
    "role": "user",
    "content": "你好",
    "created_at": "2025-01-01T00:00:00"
  }
]
```

---

### POST .../sessions/{session_id}/messages

发送消息（同步模式）。

**流程：**
1. 保存用户消息到数据库（`role: "user"`）
2. 调用 `engine.reply(employee_id, name, content)` 获取 AI 回复
3. 保存助手消息到数据库（`role: "assistant"`）
4. 返回助手消息

**请求体** `MessageCreate`：

| 字段 | 类型 | 必填 |
|------|------|------|
| `content` | `str` | 是 |

**响应 201** `MessageOut`（助手回复消息）

---

### POST .../sessions/{session_id}/messages/stream

发送消息（SSE 流式模式）。

**请求体** `MessageCreate`（同上）

**响应 200** `text/event-stream`（Server-Sent Events）

SSE 事件格式：

```
event: message
data: {"text": "这是一个"}

event: message
data: {"text": "流式回复"}

event: done
data: {"id": "msg_a1b2c3d4e5f6"}
```

| 事件类型 | data 格式 | 说明 |
|----------|-----------|------|
| `message` | `{"text": "chunk"}` | 流式文本片段 |
| `done` | `{"id": "msg_id"}` | 流结束，返回完整消息 ID |

> 内部调用 `engine.reply_stream()` 获取 `AsyncGenerator[str, None]`。对于技能链（非 DIRECT）任务，回退到非流式模式，完成后一次性返回完整结果。

---

## 任务 `/api/employees/{employee_id}/tasks`

### GET .../tasks

列出指定员工的所有任务。

**响应 200** `list[TaskOut]`：

```json
[
  {
    "id": "a1b2c3d4e5f6",
    "employee_id": "a1b2c3d4",
    "type": "conversation",
    "title": "",
    "status": "pending",
    "session_id": null,
    "created_at": "2025-01-01T00:00:00",
    "updated_at": "2025-01-01T00:00:00"
  }
]
```

---

### POST .../tasks

创建任务。

**请求体** `TaskCreate`：

| 字段 | 类型 | 必填 | 默认值 |
|------|------|------|--------|
| `type` | `str` | 否 | `"conversation"` |
| `title` | `str` | 否 | `""` |

> `type` 可选值：`conversation`、`automation`。初始状态为 `pending`。

**响应 201** `TaskOut`

---

## 自动任务 `/api/employees/{employee_id}/auto-tasks`

### GET .../auto-tasks

列出指定员工的所有自动任务。

**响应 200** `list[AutoTaskOut]`：

```json
[
  {
    "id": "a1b2c3d4e5f6",
    "employee_id": "a1b2c3d4",
    "title": "每日代码审查",
    "description": "自动审查昨日提交的代码",
    "trigger_type": "cron",
    "trigger_config": "0 9 * * *",
    "instruction": "请审查昨天的所有 Git 提交...",
    "enabled": true,
    "status": "idle",
    "last_run_at": "2025-01-01T09:00:00",
    "next_run_at": "2025-01-02T09:00:00",
    "run_count": 15,
    "created_at": "2025-01-01T00:00:00"
  }
]
```

---

### POST .../auto-tasks

创建自动任务。

**请求体** `AutoTaskCreate`：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `title` | `str` | 是 | — | 任务标题 |
| `description` | `str` | 否 | `""` | 任务描述 |
| `trigger_type` | `str` | 否 | `"manual"` | 触发方式：`manual` / `cron` / `interval` |
| `trigger_config` | `str` | 否 | `""` | 触发配置（cron 表达式或间隔秒数） |
| `instruction` | `str` | 是 | — | 发送给 engine 的指令内容 |
| `enabled` | `bool` | 否 | `true` | 是否启用 |

**响应 201** `AutoTaskOut`

---

### PUT .../auto-tasks/{task_id}

更新自动任务。

**请求体** `AutoTaskUpdate`（全部可选）：

| 字段 | 类型 |
|------|------|
| `title` | `str \| None` |
| `description` | `str \| None` |
| `trigger_type` | `str \| None` |
| `trigger_config` | `str \| None` |
| `instruction` | `str \| None` |
| `enabled` | `bool \| None` |

**响应 200** `AutoTaskOut`

---

### DELETE .../auto-tasks/{task_id}

删除自动任务。

**响应 204** 无内容

---

### POST .../auto-tasks/{task_id}/trigger

手动触发执行一次自动任务。

**执行流程：**
1. 标记任务状态为 `running`
2. 在 `auto_task_runs` 表创建执行记录
3. 创建一个新会话
4. 将 `instruction` 作为用户消息保存
5. 调用 `engine.reply()` 获取回复
6. 保存助手回复
7. 更新任务状态（`completed` 或 `failed`）、`last_run_at`、`run_count`

**响应 200** `AutoTaskRunOut`：

```json
{
  "id": "run_a1b2c3d4e5f6",
  "auto_task_id": "a1b2c3d4e5f6",
  "status": "completed",
  "output": "审查完成，发现 3 个问题...",
  "started_at": "2025-01-01T09:00:00",
  "finished_at": "2025-01-01T09:02:30",
  "error": null
}
```

---

### GET .../auto-tasks/{task_id}/runs

获取自动任务的执行历史。

**响应 200** `list[AutoTaskRunOut]`

---

### 调度器

后台调度器每 **60 秒** tick 一次，执行流程：

1. 调用 `AutoTaskService.tick()`
2. 查找所有满足条件的到期任务（`enabled=true` 且 `next_run_at <= now()`）
3. 对每个到期任务执行 `run_auto_task()`
4. 执行完毕后通过 `_calc_next_run()` 计算下次执行时间：
   - `cron` 类型 — 解析 cron 表达式
   - `interval` 类型 — 当前时间 + 间隔秒数

---

## 模板 `/api/templates`

### GET /api/templates

列出所有可用的 Agent 模板。扫描 `agents/templates/` 下的子目录，读取每个子目录中的 `config.yaml`。

**响应 200** `list[dict]`：

```json
[
  {
    "id": "developer",
    "title": "开发工程师",
    "description": "全栈开发助手，擅长代码编写与调试",
    "knowledge": ["python", "javascript", "sql"]
  }
]
```

---

## 文件 `/api/employees/{employee_id}/files`

操作员工实例目录（`~/.agent-smith/employees/<id>/`）下的配置文件。

### 白名单

仅允许操作以下文件：

- `role.md`
- `style.md`
- `workflow.md`
- `config.yaml`

访问白名单之外的文件返回 `400`。

---

### GET .../files

列出员工目录下的所有文件。

**响应 200**：

```json
["role.md", "style.md", "workflow.md", "config.yaml", "context.md"]
```

---

### GET .../files/{filename}

读取指定文件内容。

**路径参数：**
- `filename` — 文件名（必须在白名单内）

**响应 200：**

```json
{
  "filename": "role.md",
  "content": "# 角色定义\n\n你是一名全栈开发工程师..."
}
```

---

### PUT .../files/{filename}

更新指定文件内容。

**请求体** `FileContent`：

| 字段 | 类型 | 必填 |
|------|------|------|
| `content` | `str` | 是 |

**响应 200：**

```json
{
  "filename": "role.md",
  "content": "# 角色定义\n\n更新后的内容..."
}
```

---

## 配置 `/api/config`

### GET /api/config/llm

获取当前 LLM 配置。读取 `~/.agent-smith/config.yaml`。

> `api_key` 字段被隐藏，不会返回给前端。

**响应 200：**

```json
{
  "configured": true,
  "model": "gpt-4o-mini",
  "base_url": "https://api.openai.com/v1"
}
```

---

### POST /api/config/llm

设置 LLM 配置。写入 `~/.agent-smith/config.yaml`。

**请求体** `LLMConfig`：

| 字段 | 类型 | 必填 | 默认值 |
|------|------|------|--------|
| `api_key` | `str` | 是 | — |
| `base_url` | `str \| None` | 否 | `None` |
| `model` | `str` | 否 | `"gpt-4o-mini"` |

**响应 200：**

```json
{
  "status": "ok",
  "model": "gpt-4o-mini"
}
```

---

## 统计 `/api/employees/{employee_id}/stats`

### GET .../stats

获取指定员工的活动统计数据。

**响应 200：**

```json
{
  "employee_id": "a1b2c3d4",
  "days_active": 30,
  "total_sessions": 42,
  "total_messages": 356,
  "total_tasks": 18,
  "completed_tasks": 15,
  "auto_tasks": 3,
  "recent_activity": [
    {
      "session_id": "a1b2c3d4e5f6",
      "title": "代码审查",
      "created_at": "2025-01-01T10:00:00",
      "message_count": 12
    }
  ],
  "activity_heatmap": {
    "2025-01-01": 5,
    "2025-01-02": 3,
    "2024-12-31": 8
  },
  "tool_usage": {
    "file_read": 45,
    "web_search": 12,
    "code_execute": 28
  }
}
```

| 字段 | 说明 |
|------|------|
| `days_active` | 有活动的天数 |
| `total_sessions` | 会话总数 |
| `total_messages` | 消息总数 |
| `total_tasks` | 任务总数 |
| `completed_tasks` | 已完成任务数 |
| `auto_tasks` | 自动任务数 |
| `recent_activity` | 最近 10 个会话 |
| `activity_heatmap` | 近 30 天每日消息数 |
| `tool_usage` | 从助手消息中解析的工具调用统计 |

---

## 插件 `/api/plugins`

### GET /api/plugins

列出所有已注册的插件及其启用状态。

**响应 200：**

```json
[
  {
    "name": "github",
    "enabled": true,
    "description": "GitHub 集成插件"
  }
]
```

---

### POST /api/plugins/{name}/webhook

接收外部 webhook 事件。

**路径参数：**
- `name` — 插件名称

**请求体：** 任意 JSON

**请求头（可选）：**
- `X-GitHub-Event` — GitHub 事件类型（如存在则传递给插件处理）

**响应 200：** 插件处理结果

> 插件支持两种触发方式：`PollingTrigger`（主动轮询）和 `WebhookTrigger`（被动接收）。

---

### POST /api/plugins/{name}/enable

启用指定插件。

**响应 200：**

```json
{
  "status": "enabled",
  "plugin": "github"
}
```

---

### POST /api/plugins/{name}/disable

禁用指定插件。

**响应 200：**

```json
{
  "status": "disabled",
  "plugin": "github"
}
```

---

## 团队 `/api/teams`

### POST /api/teams

创建团队群组。

**请求体** `TeamGroupCreate`：

| 字段 | 类型 | 必填 | 默认值 |
|------|------|------|--------|
| `name` | `str` | 是 | — |
| `description` | `str` | 否 | `""` |
| `member_ids` | `list[str]` | 否 | `[]` |

> 群组 ID 为 `uuid4().hex[:8]`。

**响应 201** `TeamGroupOut`：

```json
{
  "id": "g1a2b3c4",
  "name": "核心开发组",
  "description": "负责核心功能开发",
  "member_ids": ["a1b2c3d4", "e5f6g7h8"],
  "created_at": "2025-01-01T00:00:00"
}
```

---

### GET /api/teams

列出所有团队群组。

**响应 200** `list[TeamGroupOut]`

---

### GET /api/teams/{group_id}

获取指定团队群组详情。

**响应 200** `TeamGroupOut`

---

### DELETE /api/teams/{group_id}

删除团队群组。

**响应 204** 无内容

---

### GET /api/teams/{group_id}/messages

获取团队消息列表。

**查询参数：**

| 参数 | 类型 | 默认值 |
|------|------|--------|
| `limit` | `int` | `50` |

**响应 200** `list[TeamMessageOut]`：

```json
[
  {
    "id": "tm_a1b2c3d4e5f6",
    "group_id": "g1a2b3c4",
    "sender_id": "user",
    "sender_name": "用户",
    "content": "@小智 请审查这段代码",
    "mentions": ["a1b2c3d4"],
    "created_at": "2025-01-01T10:00:00"
  }
]
```

---

### POST /api/teams/{group_id}/messages

发送团队消息（同步模式）。

**消息路由逻辑：**
1. 保存用户消息
2. 提取消息中的 `@mentions`（匹配员工名称）
3. 如果有 `@mentions`，仅路由到被提及的员工
4. 如果没有 `@mentions`，路由到群组中的所有成员
5. 每个被路由的员工独立调用 `engine.reply()` 生成回复
6. 返回所有回复消息

**请求体** `TeamMessageCreate`：

| 字段 | 类型 | 必填 |
|------|------|------|
| `content` | `str` | 是 |

**响应 201** `list[TeamMessageOut]`（包含所有 Agent 回复）

---

### POST /api/teams/{group_id}/messages/stream

发送团队消息（SSE 流式模式）。

**响应 200** `text/event-stream`

SSE 事件格式：

```
event: user_message
data: {"id": "tm_xxx", "content": "..."}

event: agent_start
data: {"employee_id": "a1b2c3d4", "name": "小智"}

event: message
data: {"employee_id": "a1b2c3d4", "text": "正在分析..."}

event: agent_done
data: {"employee_id": "a1b2c3d4", "message_id": "tm_yyy"}

event: done
data: {}
```

| 事件类型 | 说明 |
|----------|------|
| `user_message` | 用户消息已保存 |
| `agent_start` | 某个 Agent 开始回复 |
| `message` | Agent 流式回复片段 |
| `agent_done` | 某个 Agent 回复完毕 |
| `done` | 所有 Agent 回复完毕 |

---

## 领域模型摘要

所有 Pydantic 模型定义位于 `server/app/domain/`，共 22 个模型。

### 认证 `domain/auth.py`

| 模型 | 字段 |
|------|------|
| `LoginRequest` | `email: EmailStr`, `password: str`（8-128 字符，含字母+数字） |
| `LoginResponse` | `success: bool`, `message: str`, `user_data: dict \| None` |
| `ValidationError` | `field: str`, `message: str` |

### 员工 `domain/employee.py`

| 模型 | 字段 |
|------|------|
| `EmployeeCreate` | `name: str`, `role: str`, `description: str = ""`, `device: str = ""`, `knowledge: list[str] = []`, `environment: str = "本地"`, `accent: str = ""` |
| `EmployeeUpdate` | `name: str \| None`, `role: str \| None`, `description: str \| None`, `device: str \| None`, `knowledge: list[str] \| None`, `online: bool \| None`, `accent: str \| None` |
| `EmployeeOut` | `id: str`, `name: str`, `role: str`, `device: str`, `online: bool`, `description: str`, `knowledge: list[str]`, `environment: str`, `accent: str`, `created_at: str` |

### 会话 `domain/session.py`

| 模型 | 字段 |
|------|------|
| `SessionCreate` | `title: str = ""` |
| `SessionOut` | `id: str`, `employee_id: str`, `title: str`, `created_at: str`, `last_message_preview: str \| None`, `last_message_at: str \| None`, `message_count: int = 0` |
| `MessageCreate` | `content: str` |
| `MessageOut` | `id: str`, `session_id: str`, `role: str`, `content: str`, `created_at: str` |

### 任务 `domain/task.py`

| 模型 | 字段 |
|------|------|
| `TaskCreate` | `type: str = "conversation"`, `title: str = ""` |
| `TaskOut` | `id: str`, `employee_id: str`, `type: str`, `title: str`, `status: str`, `session_id: str \| None`, `created_at: str`, `updated_at: str` |

### 自动任务 `domain/auto_task.py`

| 模型 | 字段 |
|------|------|
| `AutoTaskCreate` | `title: str`, `description: str = ""`, `trigger_type: str = "manual"`, `trigger_config: str = ""`, `instruction: str`, `enabled: bool = True` |
| `AutoTaskUpdate` | `title: str \| None`, `description: str \| None`, `trigger_type: str \| None`, `trigger_config: str \| None`, `instruction: str \| None`, `enabled: bool \| None` |
| `AutoTaskOut` | `id: str`, `employee_id: str`, `title: str`, `description: str`, `trigger_type: str`, `trigger_config: str`, `instruction: str`, `enabled: bool`, `status: str`, `last_run_at: str \| None`, `next_run_at: str \| None`, `run_count: int`, `created_at: str` |
| `AutoTaskRunOut` | `id: str`, `auto_task_id: str`, `status: str`, `output: str \| None`, `started_at: str`, `finished_at: str \| None`, `error: str \| None` |

### 团队 `domain/team.py`

| 模型 | 字段 |
|------|------|
| `TeamGroupCreate` | `name: str`, `description: str = ""`, `member_ids: list[str] = []` |
| `TeamGroupOut` | `id: str`, `name: str`, `description: str`, `member_ids: list[str]`, `created_at: str` |
| `TeamMessageCreate` | `content: str` |
| `TeamMessageOut` | `id: str`, `group_id: str`, `sender_id: str`, `sender_name: str`, `content: str`, `mentions: list[str]`, `created_at: str` |

### 内联模型（定义在 Router 中）

| 模型 | 位置 | 字段 |
|------|------|------|
| `LLMConfig` | `routers/config.py` | `api_key: str`, `base_url: str \| None`, `model: str = "gpt-4o-mini"` |
| `FileContent` | `routers/files.py` | `content: str` |

---

## 服务层架构

采用 DDD 分层架构，严格遵循单向依赖：

```
Router（薄壳）→ Service（编排）→ Repository（SQL）→ common.database
```

### 分层职责

| 层 | 目录 | 职责 |
|----|------|------|
| **Router** | `server/app/routers/` | 参数提取 -> 调用 Service -> 返回结果。不包含业务逻辑 |
| **Service** | `server/app/services/` | 编排层。连接 engine + infrastructure，处理业务流程 |
| **Repository** | `server/app/infrastructure/repositories/` | 持久化层。Repository 模式，SQL 语句集中在此 |
| **Domain** | `server/app/domain/` | Pydantic 模型定义，纯数据结构 |

### 服务清单

| 服务 | 文件 | 核心方法 |
|------|------|----------|
| `EmployeeService` | `employee_service.py` | `list_employees`, `get_employee`, `create_employee`（DB + 复制模板文件）, `update_employee`, `delete_employee`（DB + 清理文件） |
| `SessionService` | `session_service.py` | `list_sessions`, `create_session`（默认标题 "新对话"）, `list_messages`（分页）, `send_message`（同步 engine 回复）, `stream_message`（SSE 异步生成器） |
| `TaskService` | `task_service.py` | `list_tasks`, `create_task` |
| `AutoTaskService` | `auto_task_service.py` | CRUD + `trigger_auto_task`（手动执行）, `run_auto_task`（创建会话 -> 发指令 -> 保存回复）, `tick()`（调度入口） |
| `TeamService` | `team_service.py` | `create_group`, `list_groups`, `get_group`, `delete_group`, `get_messages`, `send_message`（@mention 路由）, `stream_message`（SSE 多 Agent）, `_extract_mentions` |
| `ConfigService` | `config_service.py` | `get_llm_config`（读 YAML + 遮蔽 api_key）, `set_llm_config`（写 YAML） |
| `TemplateService` | `template_service.py` | `list_templates`（扫描 `agents/templates/` 目录） |
| `StatsService` | `stats_service.py` | `get_employee_stats`（聚合统计 + 热力图 + 工具使用解析） |
| `PluginService` | `plugin_service.py` | `startup` / `shutdown`, `list_plugins`, `enable_plugin` / `disable_plugin`, `handle_webhook` |
| 调度器 | `scheduler.py` | `run_scheduler()`（无限循环，每 60 秒调用 `AutoTaskService.tick()`） |

### 依赖注入

无独立的 `dependencies.py` 文件。各 Router 通过 `Depends(get_<service>)` 工厂函数内联注入。

---

## 数据库 Schema

SQLite 数据库位于 `~/.agent-smith/sqlite/agent-smith.sqlite`，使用 WAL 模式并启用外键约束。

共 **8 张表**：6 张在 `common/database.py` 中随启动创建，2 张在 `team_repo.py` 中按需创建。

### employees

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | TEXT | PRIMARY KEY |
| `name` | TEXT | NOT NULL |
| `role` | TEXT | NOT NULL |
| `device` | TEXT | DEFAULT '' |
| `online` | INTEGER | DEFAULT 0 |
| `description` | TEXT | DEFAULT '' |
| `knowledge` | TEXT | DEFAULT '[]'（JSON 数组） |
| `environment` | TEXT | DEFAULT '本地' |
| `accent` | TEXT | DEFAULT '' |
| `config_path` | TEXT | DEFAULT '' |
| `created_at` | TEXT | DEFAULT CURRENT_TIMESTAMP |

### sessions

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | TEXT | PRIMARY KEY |
| `employee_id` | TEXT | FOREIGN KEY -> employees(id) |
| `title` | TEXT | DEFAULT '' |
| `created_at` | TEXT | DEFAULT CURRENT_TIMESTAMP |

### messages

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | TEXT | PRIMARY KEY |
| `session_id` | TEXT | FOREIGN KEY -> sessions(id) |
| `role` | TEXT | NOT NULL（`user` / `assistant` / `system`） |
| `content` | TEXT | NOT NULL |
| `created_at` | TEXT | DEFAULT CURRENT_TIMESTAMP |

### tasks

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | TEXT | PRIMARY KEY |
| `employee_id` | TEXT | FOREIGN KEY -> employees(id) |
| `type` | TEXT | DEFAULT 'conversation'（`conversation` / `automation`） |
| `title` | TEXT | DEFAULT '' |
| `status` | TEXT | DEFAULT 'pending'（`pending` / `running` / `completed` / `failed`） |
| `session_id` | TEXT | FOREIGN KEY -> sessions(id)，可为 NULL |
| `created_at` | TEXT | DEFAULT CURRENT_TIMESTAMP |
| `updated_at` | TEXT | DEFAULT CURRENT_TIMESTAMP |

### auto_tasks

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | TEXT | PRIMARY KEY |
| `employee_id` | TEXT | FOREIGN KEY -> employees(id) |
| `title` | TEXT | NOT NULL |
| `description` | TEXT | DEFAULT '' |
| `trigger_type` | TEXT | DEFAULT 'manual'（`manual` / `cron` / `interval`） |
| `trigger_config` | TEXT | DEFAULT '' |
| `instruction` | TEXT | NOT NULL |
| `enabled` | INTEGER | DEFAULT 1 |
| `status` | TEXT | DEFAULT 'idle'（`idle` / `running` / `completed` / `failed`） |
| `last_run_at` | TEXT | 可为 NULL |
| `next_run_at` | TEXT | 可为 NULL |
| `run_count` | INTEGER | DEFAULT 0 |
| `created_at` | TEXT | DEFAULT CURRENT_TIMESTAMP |

### auto_task_runs

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | TEXT | PRIMARY KEY |
| `auto_task_id` | TEXT | FOREIGN KEY -> auto_tasks(id) |
| `status` | TEXT | DEFAULT 'running'（`running` / `completed` / `failed`） |
| `output` | TEXT | 可为 NULL |
| `started_at` | TEXT | DEFAULT CURRENT_TIMESTAMP |
| `finished_at` | TEXT | 可为 NULL |
| `error` | TEXT | 可为 NULL |

### team_groups（按需创建）

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | TEXT | PRIMARY KEY |
| `name` | TEXT | NOT NULL |
| `description` | TEXT | DEFAULT '' |
| `member_ids` | TEXT | DEFAULT '[]'（JSON 数组） |
| `created_at` | TEXT | DEFAULT CURRENT_TIMESTAMP |

### team_messages（按需创建）

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | TEXT | PRIMARY KEY |
| `group_id` | TEXT | FOREIGN KEY -> team_groups(id) |
| `sender_id` | TEXT | NOT NULL |
| `sender_name` | TEXT | DEFAULT '' |
| `content` | TEXT | NOT NULL |
| `mentions` | TEXT | DEFAULT '[]'（JSON 数组） |
| `created_at` | TEXT | DEFAULT CURRENT_TIMESTAMP |

---

## 执行引擎集成

服务层通过 `engine/execution/agent_loop.py` 中的两个入口与 AI 引擎交互：

### reply(employee_id, name, user_message) -> str

同步回复。内部流程：

1. 从四层配置合并 LLM 参数（平台级 -> 模板级 -> 员工级 -> 会话级）
2. 加载工具/技能注册表
3. 组装 system prompt
4. 通过关键词评分路由任务类型（DIRECT / BUGFIX / FEATURE）
5. 构建技能链（SkillChain）
6. 执行 `run_agent()`：
   - **DIRECT 任务** — 单次 ReAct 循环（思考 -> 工具调用 -> 观察）
   - **BUGFIX / FEATURE 任务** — 遍历 SkillChain DAG 节点，每个节点内部执行 ReAct 循环
7. 保存对话记忆，学习用户偏好

### reply_stream(employee_id, name, user_message) -> AsyncGenerator[str, None]

流式回复。与 `reply` 相同的前置流程，区别在于：

- **DIRECT 任务** — 通过 `llm.chat_stream()` 逐 chunk yield
- **技能链任务** — 回退到非流式 `run_agent()`，完成后一次性 yield 完整结果

### 技能链（SkillChain）

定义在 `engine/execution/skill_chain.py`：

| 任务类型 | 技能链 |
|----------|--------|
| FEATURE | planning -> architecture（条件执行） -> testing-strategy -> change-validation -> code-review |
| BUGFIX | sde-debug -> planning -> testing-strategy -> change-validation -> code-review |

每个节点支持门禁检查（`gate.py`，9 种门禁类型）和回溯（`backtrack.py`）。

---

## 关键路径常量

定义在 `common/config.py`：

| 常量 | 路径 |
|------|------|
| `DATA_DIR` | `~/.agent-smith/` |
| `TEMPLATES_DIR` | `<project_root>/agents/templates/` |
| `BUILTIN_SKILLS_DIR` | `<project_root>/agents/skills/` |
| `BUILTIN_TOOLS_DIR` | `<project_root>/agents/tools/` |
| `SAFETY_RULES_PATH` | `<project_root>/agents/safety/dangerous_commands.json` |

### LLM 配置四层合并

优先级从低到高：

```
环境变量 → 平台配置 (~/.agent-smith/config.yaml) → 模板配置 → 员工配置 → 会话覆盖
```

下层覆盖上层已有字段，未填字段继承上层。由 `common/config_loader.py` 的 `resolve_llm_config()` 实现。
