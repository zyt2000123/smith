---
name: devops
version: "1.0"
trigger: domain_match
description: DevOps 领域知识 — CI/CD、容器化、可观测性、故障响应的决策启发
input: infrastructure or deployment related task
output: infrastructure analysis, pipeline design, or incident response
---

# DevOps Knowledge

## 核心原则
1. 基础设施即代码 — 所有环境配置可版本控制、可重建
2. 不可变部署 — 不在运行中的实例上改配置，重新部署
3. 可观测性三支柱 — 日志、指标、追踪缺一不可
4. 回滚优先 — 出问题先回滚再排查，不在生产调试

## 质量检查清单
- [ ] 部署流程可一键回滚
- [ ] 密钥通过 secret manager 管理，不在代码/环境变量硬编码
- [ ] 有健康检查和就绪检查
- [ ] 告警有 runbook 链接
- [ ] 容器镜像有安全扫描

## 领域能力
- **CI/CD** — 构建、测试、部署自动化
- **基础设施即代码** — Terraform/Pulumi/CloudFormation
- **容器管理** — Docker 构建优化、Kubernetes 运维
- **可观测性** — 日志聚合、指标采集、分布式追踪
- **故障响应** — 快速定位、回滚恢复、事后复盘
- **安全加固** — 密钥管理、网络策略、镜像扫描
