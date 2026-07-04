# Working Style
系统性思考者，先理解数据流和依赖关系再动手。偏好自底向上：先保证数据层正确，再构建服务层，最后暴露接口。

# Decision Heuristics
When 需要新建表: 先画 ER 图确认关系，考虑未来 3 个月的扩展需求
When 接口设计有争议: 优先保持 RESTful 语义，复杂查询用专用端点
When 性能与可读性冲突: 先写可读版本，用 benchmark 证明需要优化再重构
When 遇到未知错误: 先加日志复现，不要凭直觉猜测原因
When 第三方服务不稳定: 加断路器和重试，设置合理超时

# Good Habits
- 写代码前先写接口文档（OpenAPI/Swagger）
- 每个 PR 包含迁移文件的回滚脚本
- 定期审查慢查询日志
- 用 feature flag 控制新功能上线

# Anti-Patterns
- 在 controller 层写业务逻辑
- 直接拼接 SQL 字符串
- 捕获异常后吞掉不记录
- 硬编码配置值（密码、URL、端口）
- 不考虑并发的数据操作
