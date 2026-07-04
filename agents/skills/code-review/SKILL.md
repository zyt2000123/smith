---
name: code-review
version: "1.0"
trigger: pre_commit
description: 审查代码变更的正确性、安全性、性能和可读性
input: file diff or file path
output: structured review with findings and severity
---

# Code Review Skill

## Goal
在代码合并前发现潜在问题，确保变更质量达到团队标准。

## Review Dimensions

### 1. Correctness 正确性（权重最高）
- 逻辑是否正确处理所有输入情况
- 边界条件是否覆盖（空值、零值、极端值）
- 错误处理是否完备（不吞异常、不漏捕获）
- 并发场景是否安全

### 2. Security 安全性
- 输入是否校验和转义（SQL注入、XSS）
- 权限检查是否到位
- 敏感数据是否保护（日志不泄露、传输加密）
- 依赖是否有已知漏洞

### 3. Performance 性能
- 是否有 N+1 查询或不必要的循环
- 大数据量场景是否考虑分页/流式
- 是否有内存泄漏风险
- 缓存策略是否合理

### 4. Readability 可读性
- 命名是否清晰表意
- 复杂逻辑是否有注释
- 函数/方法是否过长（>50行需审视）
- 代码组织是否遵循项目约定

## Severity Levels
- **critical**: 必须修复才能合并（Bug、安全漏洞、数据丢失风险）
- **major**: 强烈建议修复（性能问题、错误处理缺失）
- **minor**: 建议改进（命名、注释、代码风格）
- **nit**: 可选优化（个人偏好级别的建议）

## Output Format
```
## Code Review: [文件/PR 名称]

### Summary
[一句话总结代码变更的质量评估]

### Findings

#### [severity] 问题标题
- **位置**: file:line
- **问题**: 描述发现的问题
- **建议**: 具体的修改方案
- **原因**: 为什么这是个问题

### Verdict
- [ ] APPROVE — 可以合并
- [ ] REQUEST_CHANGES — 需要修改后再审
```
