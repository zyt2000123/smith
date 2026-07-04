---
name: architecture
version: "1.0"
trigger: large_change
trigger_condition: "change affects 3+ files across 2+ modules"
description: 在大型变更前进行架构评审，确保设计合理
input: proposed change description
output: architecture decision record
---

# Architecture Skill

## Goal
在影响面较大的变更前进行架构思考，避免局部优化导致全局问题。

## Trigger Conditions
- 变更涉及 3 个以上文件
- 变更跨越 2 个以上模块
- 引入新的外部依赖
- 修改数据模型或 API 契约
- 创建新的模块或服务

## Evaluation Criteria

### 1. 一致性
- 与现有架构模式是否一致
- 是否引入了新的模式（如果是，是否有充分理由）
- 命名和分层是否遵循现有约定

### 2. 可维护性
- 模块边界是否清晰
- 依赖方向是否正确（高层不依赖低层实现细节）
- 变更是否容易测试

### 3. 可扩展性
- 是否为未来变化留有空间但不过度设计
- 接口是否足够抽象但不过度抽象
- 数据模型是否支持已知的近期需求

### 4. 安全性
- 数据流是否有适当的权限检查
- 新的攻击面是否已识别并缓解

### 5. 性能
- 是否引入了 O(n^2) 或更差的算法
- 数据库查询是否高效
- 是否有不必要的网络调用

## Output Format
```
## Architecture Decision: [决策标题]

### Context
[为什么需要做这个决策]

### Options Considered
1. [方案A]: [优缺点]
2. [方案B]: [优缺点]

### Decision
[选择哪个方案，为什么]

### Consequences
- 正面: [好处]
- 负面: [代价和风险]
- 需要后续: [TODO 项]
```
