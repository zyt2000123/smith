# Data Analyst Tools

## Data Access
- **read_file** — 读取数据文件、SQL 脚本、分析报告
- **write_file** — 创建分析脚本、报告、数据处理配置
- **shell** — 执行 SQL 查询、运行分析脚本、生成可视化

## Investigation
- **search_knowledge** — 查询数据字典、指标定义、历史分析报告
- **web_fetch** — 获取外部数据源、行业基准、统计方法文档

## Workflow
- **skill_load** — 加载 planning 技能辅助分析计划制定
- **memory_ops** — 记录指标定义、数据质量问题、分析发现

## Best Practices
- shell 执行查询前先 read_file 确认表结构和字段含义
- 大数据量查询先 LIMIT 采样验证逻辑再跑全量
- 用 memory_ops 维护数据字典和常用查询模板
