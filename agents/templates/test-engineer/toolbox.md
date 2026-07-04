# Test Engineer Tools

## Code Operations
- **read_file** — 阅读被测代码、现有测试、配置文件
- **write_file** — 创建测试文件、测试工具、fixture
- **shell** — 运行测试套件、覆盖率报告、lint 检查

## Investigation
- **search_knowledge** — 查询测试框架文档、最佳实践、已知问题
- **web_fetch** — 获取测试工具文档和技术方案

## Workflow
- **skill_load** — 加载 testing-strategy / sde-debug / code-review 技能
- **memory_ops** — 记录测试策略决策、flaky test 历史、覆盖率趋势

## Best Practices
- 写测试前先 read_file 理解被测代码的公开接口
- shell 运行测试时使用 verbose 模式以获取详细失败信息
- 用 memory_ops 跟踪 flaky test 修复历史
