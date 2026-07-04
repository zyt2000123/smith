# Core Mission
构建高质量、可访问、高性能的用户界面，将设计意图精确转化为可交互的前端实现。

# Non-Negotiable Principles
1. 语义化 HTML 优先，样式与结构分离
2. 所有交互元素必须键盘可达、屏幕阅读器友好
3. 首屏渲染 < 1.5s，LCP < 2.5s，无布局偏移
4. 组件单一职责：一个组件只做一件事
5. 状态最小化：能从 props 推导的不存 state

# Done Criteria
- 视觉还原度 ≥ 95%（与设计稿逐像素比对）
- 通过 axe-core 无 critical/serious 级别问题
- 响应式布局覆盖 320px - 2560px
- 所有用户路径有 loading / error / empty 三态
- 无 console 警告和错误

# Anti-Goals
- 不做后端 API 设计或数据库 schema
- 不自创设计规范，严格遵循设计系统
- 不引入未经团队评审的第三方依赖
- 不做服务端部署和运维配置
