# DevOps Engineer Tools

## Infrastructure
- **read_file** — 阅读 IaC 配置、CI/CD 管道定义、Dockerfile
- **write_file** — 创建和修改基础设施配置、脚本、管道文件
- **shell** — 执行部署命令、运行基础设施工具、查看日志

## Investigation
- **search_knowledge** — 查询运维文档、runbook、架构决策记录
- **web_fetch** — 获取云服务文档、工具版本更新信息

## Workflow
- **skill_load** — 加载 change-validation / planning / architecture 技能
- **memory_ops** — 记录基础设施变更历史、事故复盘、容量规划数据

## Best Practices
- shell 执行部署命令前先检查当前环境（不要在生产上测试）
- write_file 修改配置前一定先 read_file 确认当前内容
- 敏感操作先用 --dry-run 预演
