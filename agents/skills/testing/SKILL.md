---
name: testing
version: "1.0"
trigger: domain_match
description: 测试领域知识 — 测试策略、分层测试、边界分析、测试基础设施的决策启发
input: testing-related task or code
output: test strategy, test cases, or test review
---

# Testing Knowledge

## 核心原则
1. 测试金字塔 — 单元多、集成适中、E2E 少
2. 测试行为不测实现 — 重构不应导致测试大面积失败
3. 每个 bug 修复伴随回归测试 — 同一个 bug 不修两次
4. 测试数据自包含 — 不依赖外部状态或执行顺序

## 质量检查清单
- [ ] 核心路径有端到端测试覆盖
- [ ] 边界值和异常输入有专门测试
- [ ] mock 范围最小化，优先用真实依赖
- [ ] 测试命名描述行为（should_X_when_Y）
- [ ] CI 中测试可重复运行，无 flaky test

## 领域能力
- **测试策略** — 分层分配、覆盖目标、风险评估
- **单元测试** — 隔离、mock、参数化、属性测试
- **集成测试** — 数据库、API、消息队列的真实交互
- **E2E 测试** — 用户场景模拟、浏览器自动化
- **边界分析** — 等价类划分、极端输入、并发场景
- **测试基础设施** — fixture 管理、数据工厂、CI 集成
