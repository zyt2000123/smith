---
name: planning
version: "1.0"
trigger: task_start
description: 在编码前制定实现计划，将模糊需求转化为有序的执行步骤
input: task description or requirement
output: numbered implementation plan with verification points
---

# Planning Skill

## Goal
将任务拆解为可验证的执行步骤，确保每一步都有明确的输入、产出和验证标准。

## Process

### Step 1: 需求澄清
- 重述任务目标（用自己的话，确认理解）
- 识别模糊点和假设，列出需要确认的问题
- 确定成功标准：怎样算「完成」

### Step 2: 范围界定
- 列出要做的（In Scope）
- 列出不做的（Out of Scope）
- 识别依赖：需要哪些前置条件

### Step 3: 步骤分解
- 将任务拆成 3-7 个有序步骤
- 每步包含：动作描述 + 预期产出 + 验证方式
- 标注可并行的步骤

### Step 4: 风险识别
- 列出可能出错的点
- 为每个风险准备应对方案
- 标注需要技术 spike 的不确定项

### Step 5: 计划确认
- 汇总为结构化计划
- 估算每步时间范围
- 确认计划与原始需求一致

## Output Format
```
## Plan: [任务名称]

### 目标
[一句话描述成功标准]

### 步骤
1. [步骤名称]
   - 动作: [具体操作]
   - 产出: [预期结果]
   - 验证: [如何确认完成]

2. ...

### 风险
- [风险描述] → [应对方案]

### 依赖
- [前置条件或外部依赖]
```
