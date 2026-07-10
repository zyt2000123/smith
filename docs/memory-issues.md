# Memory System — Pending Issues

建议在 GitHub 建三个独立 issue，避免后面边审查边顺手改。

---

## Issue 1: Dream redesign

**Title:** Dream redesign: operate on durable.md instead of scattered .md entries

Dream 已暂停。当前 `DreamConsolidator` 操作 `FileMemoryStore` 的散落 `.md`，但新写入只走 `recent.jsonl`，数据模型不对齐。

**新职责：**
1. 压缩 durable.md 冗余表达
2. 合并重复/近义事实
3. 识别跨事件稳定 pattern
4. 清理增量编译遗漏的过时内容
5. 提议可能值得生成 episode 的主题

**约束：** 不改 recent.jsonl、不写交互偏好、不过度归纳、低频触发（每天或每 50 事件）

**文件：** dream.py 重写, store.py 重新接入, 考虑移除 FileMemoryStore

---

## Issue 2: Episode lifecycle

**Title:** Episode lifecycle: trigger mechanism and FTS5 indexing

`compact_episode()` 已实现但无触发机制。

**第一版触发条件：**
1. 用户明确要求"整理一下这段过程"
2. 任务状态变为完成
3. recent.md 即将淘汰有价值的历史记录

**格式：** `episodes/{slug}.md`，按主题命名不按时间。

**检索预算：** 最多 3 篇，6000 字符上限。

**文件：** compile.py, store.py (增量索引), search.py (持久化索引), CLI 手动触发

---

## Issue 3: Preference/context boundary

**Title:** Preference/context boundary: context.md vs durable.md dedup

`context.md`（UserPreferenceLearner）和 `durable.md`（compile_durable）都可能存用户偏好。

**待做：**
1. 验证 compile_durable prompt 的偏好排除是否生效
2. 考虑 context.md → preferences.md 重命名
3. 考虑结构化格式（YAML）
4. 跑几次真实对话验证无偏好泄漏到 durable.md

**文件：** user_learner.py, assembler.py (Layer 6), compile.py

---

## 下一轮优先级

```
context.md 边界 → episodes 触发 → Dream 重设计 → 审查 engine 其他模块
```
