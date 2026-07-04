# Backend Engineer Tools

## Code Editing
- **read_file** — 阅读现有服务代码、配置、迁移文件
- **write_file** — 创建新的模型、服务、路由、测试文件
- **shell** — 运行测试、数据库迁移、代码检查

## Investigation
- **search_knowledge** — 查询 API 文档、数据库 schema、架构决策记录
- **web_fetch** — 获取第三方服务文档和技术方案

## Workflow
- **skill_load** — 加载 planning / code-review / sde-debug / architecture 技能
- **memory_ops** — 记录架构决策、接口变更历史、已知问题

## Best Practices
- 修改数据库 schema 前先 read_file 检查现有迁移历史
- shell 执行数据库操作时务必在事务中进行
- 涉及外部服务调用时检查超时配置
