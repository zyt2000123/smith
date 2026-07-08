---
name: data-analysis
version: "1.0"
trigger: domain_match
description: 数据分析领域知识 — 探索性分析、SQL、可视化、统计检验、指标设计
input: data-related task or question
output: data analysis, visualization recommendation, or metric design
---

# Data Analysis Knowledge

## 核心原则
1. 先看分布再下结论 — 均值可能骗人，要看中位数和分位数
2. 相关不等于因果 — A/B 测试前不下因果判断
3. 图表服务于结论 — 每张图回答一个问题
4. 数据质量是前提 — 脏数据上的分析毫无意义

## 质量检查清单
- [ ] 数据源和时间范围已明确
- [ ] 空值和异常值已处理并说明处理方式
- [ ] 统计结论有置信水平
- [ ] 图表有标题、坐标轴标签、数据来源标注
- [ ] 分析可复现（SQL/代码可重跑）

## 领域能力
- **探索性分析** — 分布检查、趋势识别、异常发现
- **SQL 分析** — 复杂查询、窗口函数、CTE、性能优化
- **数据可视化** — 图表类型选择、标注、配色
- **统计检验** — A/B 测试、假设检验、置信区间
- **指标设计** — 北极星指标、漏斗分析、留存分析
- **数据质量** — 数据验证、清洗规则、一致性检查
