---
name: frontend
version: "1.0"
trigger: domain_match
description: 前端领域知识 — 组件开发、布局、性能、无障碍的决策启发和质量检查清单
input: frontend-related task or code
output: domain-informed analysis or implementation
---

# Frontend Knowledge

## 核心原则
1. 语义化 HTML 优先，样式与结构分离
2. 所有交互元素必须键盘可达、屏幕阅读器友好
3. 首屏 LCP < 2.5s，无布局偏移（CLS < 0.1）
4. 组件单一职责，状态最小化（能从 props 推导的不存 state）

## 质量检查清单
- [ ] 响应式覆盖 320px - 2560px
- [ ] 所有路径有 loading / error / empty 三态
- [ ] axe-core 无 critical/serious 问题
- [ ] 无 console 警告和错误
- [ ] 代码分割合理，无不必要的全量导入

## 领域能力
- **组件开发** — React/Vue 组件，状态管理，生命周期
- **响应式布局** — 移动端到桌面端适配
- **性能调优** — 代码分割、懒加载、渲染优化
- **无障碍** — 语义 HTML、ARIA、键盘导航
- **CSS 工程** — 模块化、主题切换、动画

## 边界
- 不做后端 API 设计或数据库 schema
- 不自创设计规范，遵循现有设计系统
- 不引入未评审的第三方依赖
