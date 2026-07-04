---
name: testing-strategy
version: "1.0"
trigger: pre_implement
description: 为功能或变更定义测试策略，确定测试层级和覆盖目标
input: feature description or change scope
output: test strategy with test cases
---

# Testing Strategy Skill

## Goal
在编码前或编码中制定测试策略，确保测试投入产出比最优。

## Test Level Selection

### Unit Test（单元测试）
- **适用**: 纯函数、算法、数据转换、业务规则
- **覆盖目标**: 所有公开方法，重点是边界条件
- **不适用**: UI 渲染、外部服务调用、数据库操作

### Integration Test（集成测试）
- **适用**: 数据库操作、API 端点、跨模块调用
- **覆盖目标**: 正常流程 + 主要异常路径
- **不适用**: 纯逻辑计算、UI 布局

### E2E Test（端到端测试）
- **适用**: 核心用户流程、支付等关键路径
- **覆盖目标**: Happy path + 最重要的异常路径
- **不适用**: 边界值测试、性能测试

## Coverage Requirements
- 关键业务逻辑: ≥ 90% 分支覆盖
- 普通业务逻辑: ≥ 70% 行覆盖
- 工具函数: ≥ 80% 分支覆盖
- UI 组件: 关键交互有测试即可

## Edge Case Identification Checklist
- 空值/null/undefined
- 空集合/空字符串
- 单元素集合
- 最大值/最小值/溢出
- 并发/竞态条件
- 超时/网络中断
- 非法输入格式
- Unicode/特殊字符

## Output Format
```
## Test Strategy: [功能名称]

### Test Pyramid
- Unit: [数量] tests — [覆盖什么]
- Integration: [数量] tests — [覆盖什么]
- E2E: [数量] tests — [覆盖什么]

### Key Test Cases
1. [测试名称]: [Given-When-Then]
2. ...

### Edge Cases
- [边界情况]: [测试方法]

### Not Testing (and why)
- [排除项]: [原因]
```
