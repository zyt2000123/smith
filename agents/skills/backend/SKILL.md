---
name: backend
version: "1.0"
trigger: domain_match
description: 后端领域知识 — API 设计、数据库、安全、性能的决策启发和质量检查清单
input: backend-related task or code
output: domain-informed analysis or implementation
---

# Backend Knowledge

## 核心原则
1. API 先定义契约再实现，向后兼容优先
2. 数据库变更必须有迁移脚本，不允许手动 DDL
3. 认证授权分层处理，不在业务逻辑中硬编码权限
4. 所有外部调用必须有超时、重试和降级策略

## 质量检查清单
- [ ] API 响应有一致的错误格式（code + message + detail）
- [ ] 数据库查询有索引覆盖，无 N+1 问题
- [ ] 敏感数据不出现在日志和错误响应中
- [ ] 有健康检查端点和关键指标暴露
- [ ] 并发场景有正确的锁或幂等处理

## 领域能力
- **API 开发** — RESTful/GraphQL 设计，版本管理，文档生成
- **数据库设计** — 建模、迁移管理、查询优化
- **安全实现** — JWT/OAuth/RBAC，数据加密
- **性能调优** — 缓存策略、连接池、异步处理
- **错误处理** — 错误码体系、日志追踪、优雅降级
- **服务集成** — 第三方对接：支付、消息、存储、认证

## 边界
- 不做前端组件和样式实现
- 不自行决定产品需求和优先级
- 不在未备份的生产环境直接操作数据
