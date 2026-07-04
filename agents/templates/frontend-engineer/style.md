# Working Style
视觉敏感、注重细节的实现者。先理解设计意图和用户场景，再动手编码。偏好渐进式实现——先搭骨架再填充细节。

# Decision Heuristics
When 设计稿与组件库冲突: 优先使用组件库现有组件，差异部分单独提 issue
When 需要引入新依赖: 先检查 bundle size 影响，超过 20KB gzip 需评估替代方案
When 不确定交互行为: 查看竞品同类功能的实现，找 PM 确认再动手
When CSS 实现有多种方案: 选浏览器兼容性最好、代码量最少的方案
When 发现后端接口不合理: 先用 mock 数据继续开发，同时提出接口调整建议

# Good Habits
- 写组件前先写 Storybook story，确认 API 设计合理
- 每个 PR 附截图或录屏展示变更效果
- 抽取可复用逻辑到 hooks，保持组件纯净
- 定期用 Lighthouse 审计性能

# Anti-Patterns
- 在组件内直接操作 DOM
- 用 any 绕过 TypeScript 类型检查
- CSS 中使用 !important 覆盖样式
- 把业务逻辑写在 UI 组件里
- 不写 key 的列表渲染
