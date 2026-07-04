---
name: change-validation
version: "1.0"
trigger: pre_review
description: 在提交审查前验证变更的完整性和正确性
input: changed files list
output: validation report with pass/fail status
---

# Change Validation Skill

## Goal
在代码提交审查前做自动化检查，确保基本质量达标。

## Validation Checks

### 1. Build Check 构建检查
- 代码能否正常编译/构建
- 无类型错误（TypeScript/mypy/等）
- 无 lint 错误（仅检查变更文件）

### 2. Test Check 测试检查
- 现有测试全部通过
- 新增代码有对应测试
- 测试覆盖率不低于基线

### 3. Regression Check 回归检查
- 变更未破坏现有功能
- 依赖此代码的下游功能正常
- 数据库迁移可正向和反向执行

### 4. Convention Check 规范检查
- 文件命名符合项目约定
- 目录结构正确
- 提交信息格式规范

### 5. Safety Check 安全检查
- 无硬编码的密钥或凭证
- 无调试代码遗留（console.log、debugger、TODO hack）
- 依赖包无已知高危漏洞

## Output Format
```
## Validation Report

### Status: PASS / FAIL

### Results
| Check | Status | Details |
|-------|--------|---------|
| Build | pass/fail | ... |
| Tests | pass/fail | ... |
| Regression | pass/fail | ... |
| Convention | pass/fail | ... |
| Safety | pass/fail | ... |

### Blocking Issues
- [必须修复的问题]

### Warnings
- [建议修复但不阻塞的问题]
```
