---
name: ui-design
version: "1.0"
trigger: domain_match
description: UI 设计领域知识 — 视觉设计、交互设计、设计系统、无障碍设计的决策启发
input: design-related task or question
output: design analysis, specification, or review
---

# UI Design Knowledge

## 核心原则
1. 一致性优先 — 复用设计系统组件，不造新模式
2. 信息层级清晰 — 视觉权重引导用户注意力
3. 响应式优先设计 — 从移动端开始，渐进增强
4. 无障碍是基线 — 对比度 ≥ 4.5:1，焦点可见，语义明确

## 质量检查清单
- [ ] 颜色对比度符合 WCAG AA（正文 4.5:1，大字 3:1）
- [ ] 交互元素有 hover / active / focus / disabled 四态
- [ ] 间距和字号使用设计 token，不用硬编码值
- [ ] 动效有 prefers-reduced-motion 适配
- [ ] 空状态、加载态、错误态有设计

## 领域能力
- **视觉设计** — 布局、配色、字体、图标系统
- **交互设计** — 状态转换、动效规格、反馈机制
- **设计系统** — 组件定义、设计 token、使用指南
- **响应式设计** — 跨设备适配、断点策略
- **原型制作** — 可交互原型、用户流程演示
