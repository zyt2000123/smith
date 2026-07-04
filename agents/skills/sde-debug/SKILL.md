---
name: sde-debug
version: "1.0"
trigger: on_error
description: 结构化调试，从现象出发追踪到根因
input: error description, stack trace, or unexpected behavior
output: root cause analysis with fix
---

# SDE Debug Skill

## Goal
用系统化的方法定位和修复问题，不靠直觉猜测，用证据说话。

## Iron Rule
不修复没有确认根因的问题。「能跑了」不等于「修好了」。

## Process

### Phase 1: Reproduce 复现
- 确认复现步骤（输入、操作、环境）
- 记录准确的错误信息和堆栈
- 确认问题的可重复性（必现 / 概率 / 特定条件）
- 如果不能复现，增加日志后等待再次出现

### Phase 2: Hypothesize 假设
- 基于现象提出 2-3 个可能的原因
- 按可能性排序（从最可能到最不可能）
- 为每个假设设计验证实验

### Phase 3: Verify 验证
- 逐一验证假设（从最可能的开始）
- 用最小侵入的方式收集证据（日志 > 断点 > 代码修改）
- 确认根因后，验证它能解释所有观察到的现象
- 如果当前假设无法解释全部现象，回到 Phase 2

### Phase 4: Fix 修复
- 编写能触发 bug 的测试
- 实现最小化修复（只修根因，不「顺便」改其他）
- 确认测试从 fail 变 pass
- 检查修复是否引入新问题

## Evidence Requirements
- 每个结论都需要对应的证据（日志片段、变量值、测试结果）
- 「我觉得」不是证据，「日志显示第 42 行 x=null」是证据

## Output Format
```
## Debug Report

### Symptom
[现象描述]

### Root Cause
[根因描述 + 证据]

### Fix
[修复方案]

### Regression Test
[测试描述]

### Prevention
[如何避免同类问题再次出现]
```
