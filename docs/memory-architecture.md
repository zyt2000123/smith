# Memory Architecture

## 数据模型

```
memory/
├── recent.jsonl       # 唯一原始事件源（只追加）
├── recent.md          # 派生：最近活动摘要（7-14天弹性，8K字符预算）
├── durable.md         # 派生：长期有效事实（LLM 增量合并）
├── context.md         # 交互偏好配置（UserPreferenceLearner 独占维护）
├── episodes/          # 派生：已结题主题的过程摘要（按主题命名）
│   └── *.md
└── .fp_*              # fingerprint 缓存（MD5，跳过无变化的编译）
```

## 四种对象

| 对象 | 回答什么 | 数据源 | 生命周期 |
|---|---|---|---|
| `recent.jsonl` | 发生了什么 | 每次有工具调用的对话自动追加 | 只追加，不改写 |
| `durable.md` | 现在仍然成立什么 | LLM 从 recent 事件增量提取 | 每 5 次对话编译，LLM 合并更新 |
| `episodes/*.md` | 一段经历如何发展 | 任务完成或手动触发时生成 | 按主题归档，不自动生成 |
| `context.md` | 应该如何与用户交互 | UserPreferenceLearner 正则检测 | 独立于记忆系统 |

## 编译流程

```
对话结束（had_tools=True）
  → 追加 recent.jsonl
  → 计数器 +1
  → 到 5 次？
      → compile_recent()   : recent.jsonl → recent.md
      → compile_durable()  : 旧 durable.md + 新事件 → 新 durable.md
```

## Prompt 注入顺序

```
Layer 1-7: 身份 / 风格 / 工作流 / 工具箱 / 技能目录 / 用户上下文 / 输出规范
Layer 8:   durable.md（始终注入）
           + FTS5 检索的 episodes（按需注入，最多 3 篇，6K 字符上限）
           + recent.md（始终注入）
Layer 9:   运行时上下文
```

## 冲突优先级

```
用户当前消息 > context.md > recent.md > episodes > durable.md
```

## 当前状态

- Dream 整理：暂时断开，待重设计为低频维护 durable.md
- Episodes：compact_episode() 已实现，触发机制待建
- FileMemoryStore：保留供 memory_ops 工具使用，不在主写入链路
- 旧散落 .md 条目：只读遗留数据，不再新增
